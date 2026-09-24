"""B6：把内部 `ItineraryPlan` 富化成七部分 `TravelGuide`。

`AGENTS.md`「建议代码边界」把 `backend/app/guide/` 划归 B 线（GuideComposer）。

**内部对象与展示对象禁止混用**（`AGENTS.md` 项目原则）：
`PlanNode` / `DayPlan` 是内部精简对象，只存 `resource_id`；
用户要看到的是名称、地址、开放窗口、最晚进入、预约要求、费用和提示 ——
这些字段 `GuideComposer` 从**资源候选与证据**里取，不是从模型记忆里编。

组装规则全部从 `fixtures/valid/itinerary_plan.json` 与
`fixtures/valid/travel_guide.json` 的**内部一致性**反推得到，逐条写在
`_node_cost` / `build_guide_day` 的注释里，可对照 fixture 验算：

```text
GuideNode.estimated_cost = 该节点 cost_item 的单价（不乘 quantity）
                           无 cost_item → 抵达/返程日用 arrival/return_plan.estimated_cost
                           再没有 → 资源候选自带价格（如 restaurant.price_per_person）
GuideDay.total_activity_minutes = Σ(node.end_at - node.start_at)
GuideDay.total_travel_minutes   = Σ(leg.duration_minutes)
                                  + 抵达日 arrival_plan.duration_minutes
                                  + 返程日 return_plan.duration_minutes
GuideDay.estimated_cost         = Σ(GuideNode.estimated_cost) + Σ(leg 引用 cost_item 的单价)
```
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.schemas import (
    AlternativePlan,
    ArrivalAndDepartureSection,
    ArrivalPlan,
    BudgetAndAlternativesSection,
    Conflict,
    CostItem,
    DataAssuranceStatus,
    DataSnapshot,
    Evidence,
    GuideDay,
    GuideNode,
    GuideReadiness,
    IntercityOption,
    ItineraryPlan,
    LodgingAreaCandidate,
    LodgingCandidate,
    LodgingSection,
    Money,
    PlanNode,
    PlanValidationStatus,
    PreparationItem,
    PreparationSection,
    RestaurantCandidate,
    ReturnPlan,
    RunMode,
    SourcesAndFreshnessSection,
    TravelGuide,
    TravelLeg,
    TripProfile,
    TripSummarySection,
    VisitPlaceCandidate,
)

logger = logging.getLogger(__name__)

#: 没有资源可回指时给节点一个中性名称（不编造景点名）
NODE_TYPE_LABELS: dict[str, str] = {
    "ARRIVAL": "抵达",
    "CHECK_IN": "入住",
    "ATTRACTION": "游玩",
    "MEAL": "用餐",
    "REST": "休息",
    "WALK_AREA": "街区漫步",
    "SHOPPING": "购物",
    "LODGING": "回到住宿",
    "FREE_TIME": "自由活动",
}

#: `PlanNode.node_type` 里属于「行程骨架」而非「游玩内容」的类型
_SKELETON_TYPES = frozenset({"ARRIVAL", "CHECK_IN", "REST", "LODGING", "FREE_TIME"})

#: 强度阈值（分钟，含活动 + 通勤）
_INTENSITY_HIGH_MINUTES = 600
_INTENSITY_LOW_MINUTES = 360

#: 费用未知时的占位金额。契约的 `Money` 没有「未知」表达方式，
#: 因此额外把节点记进 `sources_and_freshness.unknown_items` 并在 tips 里明说。
_UNKNOWN_COST = Money(amount=0, currency="CNY")
_UNKNOWN_COST_TIP = "费用未知：当前数据源没有该项目的价格"


class GuideCompositionError(RuntimeError):
    """组装所需的素材缺失。

    `ArrivalAndDepartureSection.recommended_option` 是**必填**字段，
    城际交通还没接入（`get_intercity_options` 属 A 线 P1）时无法构造合法攻略。
    此时明确报错，而不是伪造一班车。
    """


@dataclass
class GuideContext:
    """Composer 需要的展示素材。全部来自数据层 / MCP / RAG，不含模型记忆。"""

    visit_places: Sequence[VisitPlaceCandidate] = ()
    restaurants: Sequence[RestaurantCandidate] = ()
    lodgings: Sequence[LodgingCandidate] = ()
    #: 区域候选，用 `resource_id` 反查 `area_id` 对应的中文区域名
    lodging_areas: Sequence[LodgingAreaCandidate] = ()
    evidence: Sequence[Evidence] = ()
    intercity_options: Sequence[IntercityOption] = ()
    arrival_plan: ArrivalPlan | None = None
    return_plan: ReturnPlan | None = None
    preparation_items: Sequence[PreparationItem] = ()
    refresh_before_departure: Sequence[PreparationItem] = ()
    alternative_plans: Sequence[AlternativePlan] = ()
    conflicts: Sequence[Conflict] = ()
    #: 目的地 ID → 中文名（A 线的覆盖数据；缺失时退回 ID 本身）
    destination_names: Mapping[str, str] = field(default_factory=dict)
    data_snapshot: DataSnapshot | None = None
    degraded_items: Sequence[str] = ()
    mock_items: Sequence[str] = ()
    unknown_items: Sequence[str] = ()
    major_tradeoffs: Sequence[str] = ()

    def has_preparation(self) -> bool:
        return bool(self.preparation_items)


# --- 入口 -------------------------------------------------------------------


def compose_travel_guide(
    plan: ItineraryPlan,
    profile: TripProfile,
    context: GuideContext,
    *,
    run_mode: RunMode,
    lifecycle_status: str = "DRAFT",
    guide_id: str | None = None,
    guide_version: int = 1,
    parent_guide_version: int | None = None,
    overall_theme: str | None = None,
    overall_reason: str | None = None,
    data_assurance_status: DataAssuranceStatus | None = None,
) -> TravelGuide:
    """把内部行程 + 数据层素材组装成七部分攻略。

    只用传入的数据；任何取不到的字段都按「未知」显式呈现，不补默认事实。
    """

    index = _ResourceIndex.from_context(context)
    days = build_guide_days(plan, context=context, index=index)
    day_warnings = [warning for day in days for warning in day.warnings]
    unknown_items = list(context.unknown_items)
    for day in days:
        for node in day.nodes:
            if _UNKNOWN_COST_TIP in node.tips:
                unknown_items.append(f"cost:{node.node_id}")

    assurance = data_assurance_status or derive_data_assurance_status(
        run_mode=run_mode,
        degraded_items=context.degraded_items,
        mock_items=context.mock_items,
    )
    has_error_conflict = any(item.severity == "ERROR" for item in context.conflicts)

    return TravelGuide(
        guide_id=guide_id or f"guide_{uuid.uuid4().hex[:12]}",
        guide_version=guide_version,
        parent_guide_version=parent_guide_version,
        session_id=plan.session_id,
        run_mode=run_mode,
        lifecycle_status=lifecycle_status,  # type: ignore[arg-type]
        plan_validation_status=plan.plan_validation_status,
        data_assurance_status=assurance,
        guide_readiness=derive_guide_readiness(
            plan_validation_status=plan.plan_validation_status,
            data_assurance_status=assurance,
            run_mode=run_mode,
            has_error_conflict=has_error_conflict,
            has_warnings=bool(day_warnings or context.degraded_items),
        ),
        timezone=plan.timezone,
        trip_summary=build_trip_summary(
            plan=plan,
            profile=profile,
            context=context,
            overall_theme=overall_theme,
            overall_reason=overall_reason,
        ),
        arrival_and_departure=build_arrival_and_departure(plan=plan, context=context),
        preparation=PreparationSection(
            items=list(context.preparation_items),
            refresh_before_departure=list(context.refresh_before_departure),
        ),
        lodging=LodgingSection(
            stay_segments=list(plan.stay_segments),
            primary_candidates=_primary_lodgings(plan, index),
            alternative_candidates=_alternative_lodgings(plan, index),
        ),
        daily_itinerary=days,
        budget_and_alternatives=BudgetAndAlternativesSection(
            # 透传规划器算出的汇总，保证与 CostItem[] 完全一致（契约校验会复算）
            budget_summary=plan.budget_summary,
            alternative_plans=list(context.alternative_plans),
        ),
        sources_and_freshness=build_sources_and_freshness(
            context=context,
            unknown_items=unknown_items,
            last_updated=datetime.now().astimezone(),
        ),
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        data_snapshot_id=plan.data_snapshot_id,
    )


# --- 每日行程 ---------------------------------------------------------------


def build_guide_days(
    plan: ItineraryPlan,
    *,
    context: GuideContext,
    index: "_ResourceIndex",
) -> list[GuideDay]:
    node_by_id = {node.node_id: node for node in plan.nodes}
    leg_by_id = {leg.leg_id: leg for leg in plan.travel_legs}
    cost_by_id = {item.cost_item_id: item for item in plan.cost_items}
    last_date = plan.end_date

    days: list[GuideDay] = []
    for day_plan in sorted(plan.days, key=lambda item: item.date):
        nodes = [node_by_id[node_id] for node_id in day_plan.node_ids if node_id in node_by_id]
        nodes.sort(key=lambda node: node.start_at)
        legs = [leg_by_id[leg_id] for leg_id in day_plan.travel_leg_ids if leg_id in leg_by_id]

        is_first = day_plan.date == plan.start_date
        is_last = day_plan.date == last_date
        stay = _stay_for_day(plan, day_plan.stay_segment_id)

        guide_nodes: list[GuideNode] = []
        for position, node in enumerate(nodes):
            is_tail = position == len(nodes) - 1
            guide_nodes.append(
                enrich_node(
                    node,
                    plan=plan,
                    context=context,
                    index=index,
                    cost_by_id=cost_by_id,
                    is_first_day=is_first,
                    is_last_day=is_last,
                    is_tail_node=is_tail,
                )
            )

        # 当日费用 = 各节点单价 + 各段交通单价（与 fixture 的算式一致，见模块 docstring）
        estimated_cost = _sum_money(
            [item.estimated_cost for item in guide_nodes]
            + [
                cost_by_id[cost_id].unit_price
                for leg in legs
                for cost_id in leg.cost_item_ids
                if cost_id in cost_by_id
            ]
        )

        activity_minutes = sum(
            _minutes_between(node.start_at, node.end_at) for node in nodes
        )
        travel_minutes = sum(leg.duration_minutes for leg in legs)
        if is_first and context.arrival_plan is not None:
            # 抵达日的接驳耗时来自 `arrival_plan`（当天未必有 TravelLeg）
            travel_minutes += context.arrival_plan.duration_minutes
        if is_last and context.return_plan is not None:
            travel_minutes += context.return_plan.duration_minutes

        days.append(
            GuideDay(
                date=day_plan.date,
                day_theme=_derive_day_theme(
                    nodes=nodes, legs=legs, is_first=is_first, is_last=is_last
                ),
                activity_areas=_derive_activity_areas(
                    nodes=nodes, index=index, stay_area=stay.lodging_area if stay else None
                ),
                start_location=_endpoint_location(nodes, index, first=True)
                or (stay.lodging_area if stay else "行程起点"),
                end_location=_endpoint_location(nodes, index, first=False)
                or (stay.lodging_area if stay else "行程终点"),
                nodes=guide_nodes,
                travel_legs=legs,
                total_activity_minutes=activity_minutes,
                total_travel_minutes=travel_minutes,
                intensity_level=_derive_intensity(
                    activity_minutes + travel_minutes, nodes=nodes, legs=legs
                ),
                estimated_cost=estimated_cost,
                warnings=_derive_day_warnings(legs=legs, nodes=guide_nodes),
                alternative_plan_ids=_alternative_ids_for_day(
                    day_plan.date, plan=plan, context=context
                ),
            )
        )

    return days


def enrich_node(
    node: PlanNode,
    *,
    plan: ItineraryPlan,
    context: GuideContext,
    index: "_ResourceIndex",
    cost_by_id: Mapping[str, CostItem],
    is_first_day: bool,
    is_last_day: bool,
    is_tail_node: bool,
) -> GuideNode:
    """`PlanNode` → `GuideNode`：补上用户能看懂的展示字段。

    这里**只做查表与推导**，不产生任何新的旅游事实。
    """

    cost, tips = _node_cost(
        node,
        context=context,
        index=index,
        cost_by_id=cost_by_id,
        is_first_day=is_first_day,
        is_last_day=is_last_day,
        is_tail_node=is_tail_node,
    )

    resource = index.find(node.resource_id)
    tips.extend(_resource_tips(resource))

    return GuideNode(
        node_id=node.node_id,
        node_type=node.node_type,
        resource_id=node.resource_id,
        name=(getattr(resource, "name", None) or NODE_TYPE_LABELS.get(node.node_type, node.node_type)),
        address=getattr(resource, "address", None),
        start_at=node.start_at,
        end_at=node.end_at,
        opening_window=_opening_window_for(resource, node.start_at),
        last_entry_at=getattr(resource, "last_entry_at", None),
        reservation_required=bool(getattr(resource, "reservation_required", False)),
        estimated_cost=cost,
        reason=node.reason,
        tips=tips,
        locked=node.locked,
        evidence_ids=list(node.evidence_ids),
    )


def _node_cost(
    node: PlanNode,
    *,
    context: GuideContext,
    index: "_ResourceIndex",
    cost_by_id: Mapping[str, CostItem],
    is_first_day: bool,
    is_last_day: bool,
    is_tail_node: bool,
) -> tuple[Money, list[str]]:
    """按 fixture 反推的优先级取节点单价（见模块 docstring 的算式）。"""

    tips: list[str] = []
    for cost_id in node.cost_item_ids:
        item = cost_by_id.get(cost_id)
        if item is None:
            continue
        return item.unit_price, tips

    # 抵达 / 返程节点通常没有单独的 CostItem，费用记在 arrival/return_plan 上
    if node.node_type == "ARRIVAL" and is_first_day and context.arrival_plan is not None:
        return context.arrival_plan.estimated_cost, tips
    if is_last_day and is_tail_node and context.return_plan is not None:
        return context.return_plan.estimated_cost, tips

    resource = index.find(node.resource_id)
    price = getattr(resource, "price_per_person", None)
    if isinstance(price, Money):
        return price, tips

    tips.append(_UNKNOWN_COST_TIP)
    return _UNKNOWN_COST, tips


def _resource_tips(resource: Any) -> list[str]:
    """把资源候选里**已有的事实**翻译成出行提示。绝不补充候选里没有的信息。"""

    if resource is None:
        return []
    tips: list[str] = []

    if getattr(resource, "reservation_required", False):
        tips.append("需要提前预约")
    if getattr(resource, "last_entry_at", None) is not None:
        tips.append("注意最晚进入时间")
    if getattr(resource, "indoor", None) is True:
        tips.append("以室内为主")
    elif getattr(resource, "indoor", None) is False:
        tips.append("以室外为主")
    if str(getattr(resource, "weather_sensitivity", "")).upper() == "HIGH":
        tips.append("对天气较敏感，建议出发前复核")
    if str(getattr(resource, "physical_intensity", "")).upper() == "HIGH":
        tips.append("体力消耗较大")
    queue_note = getattr(resource, "queue_note", None)
    if isinstance(queue_note, str) and queue_note.strip():
        tips.append(queue_note.strip())
    specials = getattr(resource, "specialty_dishes", None)
    if isinstance(specials, list) and specials:
        tips.append("招牌菜：" + "、".join(str(item) for item in specials[:3]))
    return tips


def _opening_window_for(resource: Any, start_at: datetime):
    """取覆盖该节点开始时间的那一段开放窗口；取不到就退回第一段。"""

    windows = getattr(resource, "opening_windows", None)
    if not isinstance(windows, list) or not windows:
        return None
    for window in windows:
        if window.start_at <= start_at <= window.end_at:
            return window
    return windows[0]


# --- 各分节 -----------------------------------------------------------------


def build_trip_summary(
    *,
    plan: ItineraryPlan,
    profile: TripProfile,
    context: GuideContext,
    overall_theme: str | None,
    overall_reason: str | None,
) -> TripSummarySection:
    names: list[str] = []
    for segment in plan.trip_segments:
        name = context.destination_names.get(segment.destination_id) or segment.destination_id
        if name not in names:
            names.append(name)
    if not names:
        # 没有 trip_segment 时不能编一个目的地名，只能用 ID 并如实呈现
        names = ["未指定目的地"]

    tradeoffs = list(context.major_tradeoffs)
    for conflict in context.conflicts:
        if conflict.message and conflict.message not in tradeoffs:
            tradeoffs.append(conflict.message)

    return TripSummarySection(
        destination_names=names,
        start_date=plan.start_date,
        end_date=plan.end_date,
        duration_days=(plan.end_date - plan.start_date).days + 1,
        traveler_count=profile.traveler_count,
        overall_theme=overall_theme or _derive_overall_theme(profile),
        overall_reason=overall_reason or _derive_overall_reason(profile, plan),
        major_tradeoffs=tradeoffs,
    )


def build_arrival_and_departure(
    *, plan: ItineraryPlan, context: GuideContext
) -> ArrivalAndDepartureSection:
    options = list(context.intercity_options)
    if not options:
        raise GuideCompositionError(
            "缺少城际交通方案：ArrivalAndDepartureSection.recommended_option 是必填字段，"
            "当前数据源还没有 get_intercity_options 的结果（A 线 P1）。"
            "不允许伪造车次/航班，因此这里明确报缺。"
        )
    if context.arrival_plan is None or context.return_plan is None:
        raise GuideCompositionError(
            "缺少到站衔接方案：arrival_plan / return_plan 必须由数据层提供，"
            "不允许用模型记忆补写。"
        )
    return ArrivalAndDepartureSection(
        recommended_option=options[0],
        alternative_options=options[1:],
        arrival_plan=context.arrival_plan,
        return_plan=context.return_plan,
    )


def build_sources_and_freshness(
    *,
    context: GuideContext,
    unknown_items: Sequence[str],
    last_updated: datetime,
) -> SourcesAndFreshnessSection:
    snapshot = context.data_snapshot
    evidence_ids: list[str] = []
    for item in context.evidence:
        if item.evidence_id not in evidence_ids:
            evidence_ids.append(item.evidence_id)
    if snapshot is not None:
        for evidence_id in snapshot.evidence_ids:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)

    fact_record_ids = list(snapshot.planning_fact_ids) if snapshot is not None else []
    degraded = _unique([*context.degraded_items, *(snapshot.degraded_items if snapshot else [])])
    mock = _unique([*context.mock_items, *(snapshot.mock_items if snapshot else [])])
    unknown = _unique([*unknown_items, *(snapshot.unknown_items if snapshot else [])])

    return SourcesAndFreshnessSection(
        fact_record_ids=fact_record_ids,
        evidence_ids=evidence_ids,
        degraded_items=degraded,
        mock_items=mock,
        unknown_items=unknown,
        last_updated=last_updated,
    )


# --- 状态合成（ADR-0006：三类状态分开维护） ---------------------------------


def derive_data_assurance_status(
    *,
    run_mode: RunMode,
    degraded_items: Sequence[str] = (),
    mock_items: Sequence[str] = (),
) -> DataAssuranceStatus:
    """数据可信度。DEMO 模式下**不允许**声称 `VERIFIED`（`CONTRACTS.md` §14）。"""

    if run_mode is RunMode.DEMO:
        return DataAssuranceStatus.MOCK
    if mock_items:
        return DataAssuranceStatus.MOCK
    if degraded_items:
        return DataAssuranceStatus.DEGRADED
    return DataAssuranceStatus.VERIFIED


def derive_guide_readiness(
    *,
    plan_validation_status: PlanValidationStatus,
    data_assurance_status: DataAssuranceStatus,
    run_mode: RunMode,
    has_error_conflict: bool,
    has_warnings: bool,
) -> GuideReadiness:
    """合成「能不能给用户看」。

    契约的 `TravelGuide.validate_publication_state` 只写了「哪些组合非法」，
    正向规则由本函数定义（ADR-0006 三类状态分离）：

    ```text
    INVALID 计划            → NOT_READY
    INSUFFICIENT 数据       → NOT_READY
    存在 ERROR 级冲突       → NOT_READY
    DEMO 模式               → READY_WITH_WARNINGS（契约禁止 DEMO 处于 READY）
    其余：有降级/警告       → READY_WITH_WARNINGS
          全部干净           → READY
    ```
    """

    if plan_validation_status == PlanValidationStatus.INVALID:
        return GuideReadiness.NOT_READY
    if data_assurance_status == DataAssuranceStatus.INSUFFICIENT:
        return GuideReadiness.NOT_READY
    if has_error_conflict:
        return GuideReadiness.NOT_READY
    if run_mode is RunMode.DEMO:
        return GuideReadiness.READY_WITH_WARNINGS
    if has_warnings:
        return GuideReadiness.READY_WITH_WARNINGS
    return GuideReadiness.READY


# --- 推导工具 ---------------------------------------------------------------


def _sum_money(items: Sequence[Money]) -> Money:
    """金额求和：全为精确值则输出精确值，只要有一个区间就输出区间。"""

    if not items:
        return Money(amount=0, currency="CNY")
    currency = items[0].currency
    low = 0.0
    high = 0.0
    has_range = False
    for item in items:
        if item.amount is not None:
            low += item.amount
            high += item.amount
        else:
            has_range = True
            low += float(item.min_amount or 0)
            high += float(item.max_amount or 0)
    low = round(low, 2)
    high = round(high, 2)
    if has_range:
        return Money(min_amount=low, max_amount=high, currency=currency)
    return Money(amount=low, currency=currency)


def _minutes_between(start_at: datetime, end_at: datetime) -> int:
    return int((end_at - start_at).total_seconds() // 60)


def _derive_intensity(
    total_minutes: int, *, nodes: Sequence[PlanNode], legs: Sequence[TravelLeg]
) -> str:
    if "HIGH" in {str(leg.walking_burden).upper() for leg in legs}:
        return "HIGH"
    if total_minutes >= _INTENSITY_HIGH_MINUTES:
        return "HIGH"
    if total_minutes <= _INTENSITY_LOW_MINUTES:
        return "LOW"
    return "MEDIUM"


def _derive_day_theme(
    *, nodes: Sequence[PlanNode], legs: Sequence[TravelLeg], is_first: bool, is_last: bool
) -> str:
    """当日主题。

    规则基于**当天真实排了什么**，只做概括，不引入任何外部信息。
    """

    if not nodes:
        return "缓冲与休整"
    kinds = {node.node_type for node in nodes}
    if "ARRIVAL" in kinds and is_first:
        return "抵达与适应" if len(nodes) > 1 else "抵达与入住"
    if is_last:
        return "返程与缓冲"
    attractions = kinds & {"ATTRACTION", "WALK_AREA", "SHOPPING"}
    if attractions and "MEAL" in kinds:
        return "游玩与用餐"
    if attractions:
        return "城市探索"
    if "MEAL" in kinds:
        return "美食与休闲"
    if "REST" in kinds or "FREE_TIME" in kinds:
        return "休整与自由安排"
    if legs:
        return "移动与衔接"
    return "当日安排"


def _derive_activity_areas(
    *,
    nodes: Sequence[PlanNode],
    index: "_ResourceIndex",
    stay_area: str | None,
) -> list[str]:
    areas: list[str] = []
    for node in nodes:
        resource = index.find(node.resource_id)
        area_id = getattr(resource, "area_id", None)
        if isinstance(area_id, str) and area_id.strip():
            name = index.area_names.get(area_id, area_id)
            if name not in areas:
                areas.append(name)
    if not areas:
        areas.append(stay_area or "住宿周边")
    return areas


def _endpoint_location(
    nodes: Sequence[PlanNode], index: "_ResourceIndex", *, first: bool
) -> str | None:
    if not nodes:
        return None
    node = nodes[0] if first else nodes[-1]
    resource = index.find(node.resource_id)
    address = getattr(resource, "address", None)
    if isinstance(address, str) and address.strip():
        return address.strip()
    name = getattr(resource, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return NODE_TYPE_LABELS.get(node.node_type, node.node_type)


def _derive_day_warnings(
    *, legs: Sequence[TravelLeg], nodes: Sequence[GuideNode]
) -> list[str]:
    warnings: list[str] = []
    if any(leg.source == "FAKE" or leg.is_estimated for leg in legs):
        warnings.append("路线数据为模拟或估算值，出行前请用地图复核")
    unknown = [node.name for node in nodes if _UNKNOWN_COST_TIP in node.tips]
    if unknown:
        warnings.append("以下安排没有可用价格数据，费用未知：" + "、".join(unknown[:3]))
    return warnings


def _alternative_ids_for_day(
    day: date, *, plan: ItineraryPlan, context: GuideContext
) -> list[str]:
    node_dates = {node.node_id: node.start_at.date() for node in plan.nodes}
    result: list[str] = []
    for alternative in context.alternative_plans:
        if any(node_dates.get(node_id) == day for node_id in alternative.affected_node_ids):
            if alternative.alternative_plan_id not in result:
                result.append(alternative.alternative_plan_id)
    return result


def _derive_overall_theme(profile: TripProfile) -> str:
    pace_text = {"RELAXED": "轻松", "BALANCED": "均衡", "INTENSE": "紧凑"}.get(
        profile.pace, "均衡"
    )
    interests = "、".join(profile.interests[:3])
    if interests:
        return f"{pace_text}的{interests}主题之旅"
    return f"{pace_text}节奏的城市之旅"


def _derive_overall_reason(profile: TripProfile, plan: ItineraryPlan) -> str:
    parts = [
        f"{profile.start_date.isoformat()} 至 {profile.end_date.isoformat()} 共 "
        f"{(plan.end_date - plan.start_date).days + 1} 天，{profile.traveler_count} 人出行"
    ]
    if profile.pace == "RELAXED":
        parts.append("按轻松节奏安排，保留休息时间")
    elif profile.pace == "INTENSE":
        parts.append("按紧凑节奏安排，尽量多看几个地方")
    if profile.destination_mode == "SINGLE":
        parts.append("单目的地内部按游玩区域分组，减少跨区通勤")
    return "；".join(parts)


def _primary_lodgings(
    plan: ItineraryPlan, index: "_ResourceIndex"
) -> list[LodgingCandidate]:
    result: list[LodgingCandidate] = []
    for segment in plan.stay_segments:
        candidate = index.lodgings.get(segment.lodging_id)
        if candidate is not None and candidate not in result:
            result.append(candidate)
    return result


def _alternative_lodgings(
    plan: ItineraryPlan, index: "_ResourceIndex"
) -> list[LodgingCandidate]:
    used = {segment.lodging_id for segment in plan.stay_segments}
    return [item for identifier, item in index.lodgings.items() if identifier not in used]


def _stay_for_day(plan: ItineraryPlan, stay_segment_id: str):
    for segment in plan.stay_segments:
        if segment.stay_segment_id == stay_segment_id:
            return segment
    return None


def _unique(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


# --- 资源索引 ---------------------------------------------------------------


@dataclass
class _ResourceIndex:
    """按 `resource_id` 查资源候选，并支持 `area_id` → 区域中文名。"""

    visit_places: dict[str, VisitPlaceCandidate] = field(default_factory=dict)
    restaurants: dict[str, RestaurantCandidate] = field(default_factory=dict)
    lodgings: dict[str, LodgingCandidate] = field(default_factory=dict)
    area_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_context(cls, context: GuideContext) -> "_ResourceIndex":
        return cls(
            visit_places={item.resource_id: item for item in context.visit_places},
            restaurants={item.resource_id: item for item in context.restaurants},
            lodgings={item.resource_id: item for item in context.lodgings},
            area_names={
                item.resource_id: item.name for item in context.lodging_areas if item.name
            },
        )

    def find(self, resource_id: str | None) -> Any:
        if not resource_id:
            return None
        for bucket in (self.visit_places, self.restaurants, self.lodgings):
            found = bucket.get(resource_id)
            if found is not None:
                return found
        return None


__all__ = [
    "GuideCompositionError",
    "GuideContext",
    "NODE_TYPE_LABELS",
    "build_arrival_and_departure",
    "build_guide_days",
    "build_sources_and_freshness",
    "build_trip_summary",
    "compose_travel_guide",
    "derive_data_assurance_status",
    "derive_guide_readiness",
    "enrich_node",
]
