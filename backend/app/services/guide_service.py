"""C7 攻略组装：把已验证的 `ItineraryPlan` 变成用户看的七部分 `TravelGuide`。

分工说明：**组装本身是 B 线（B6）的 `app.guide.compose_travel_guide`**，
本模块只负责它要的素材——这些素材别处没人提供：

```text
ArrivalPlan / ReturnPlan   抵达与返程衔接（车站 → 住宿 / 住宿 → 车站）
PreparationItem[]          由 MCP 的 get_preparation_rules 规则翻译而来
目的地中文名                 供七部分文案使用
数据快照、冲突、mock/degraded/unknown 清单
```

**不允许伪造**：`ArrivalPlan.duration_minutes` / `estimated_cost`、`ReturnPlan` 的
同样字段都必须来自 Provider 的路线结果；拿不到就抛 `GuideDataError` 并带上缺失项代码，
由 API 层翻成统一信封里的明确错误（`CONTRACTS.md` §13）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

from app.guide import GuideCompositionError, GuideContext, compose_travel_guide
from app.schemas import (
    ArrivalPlan,
    Conflict,
    DataSnapshot,
    Evidence,
    GetPreparationRulesRequest,
    GetRouteRequest,
    GetWeatherRequest,
    IntercityOption,
    ItineraryPlan,
    LodgingAreaCandidate,
    LodgingCandidate,
    PreparationItem,
    PreparationRule,
    ResourceCandidateBase,
    RestaurantCandidate,
    ReturnPlan,
    RunMode,
    TravelGuide,
    TripProfile,
    VisitPlaceCandidate,
)

#: `TravelLeg` 的交通方式 → `ArrivalPlan` / `ReturnPlan` 允许的取值
_LOCAL_MODE = {
    "WALK": "WALK",
    "METRO": "METRO",
    "BUS": "BUS",
    "TAXI": "TAXI",
}
#: 离开住宿去车站前预留的缓冲（分钟），只在计算"最晚出发时间"时使用
_DEPARTURE_BUFFER_MINUTES = 90


class GuideDataError(Exception):
    """组装攻略所需的素材缺失（不伪造，直接报缺）。"""

    def __init__(self, message: str, *, missing: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.missing = list(missing)


@dataclass
class GuideBuildOutcome:
    guide: TravelGuide | None = None
    missing_inputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def build_guide(
    *,
    plan: ItineraryPlan,
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase],
    intercity_options: Sequence[IntercityOption],
    mcp,
    evidence: Sequence[Evidence] = (),
    preparation_rules: Sequence[PreparationRule] = (),
    conflicts: Sequence[Conflict] = (),
    data_snapshot: DataSnapshot | None = None,
    destination_names: Mapping[str, str] | None = None,
    run_mode: RunMode = RunMode.DEMO,
    lifecycle_status: str = "DRAFT",
    guide_id: str | None = None,
    guide_version: int = 1,
    parent_guide_version: int | None = None,
) -> GuideBuildOutcome:
    """组装攻略；素材不足时返回缺项而不是半个攻略。"""

    try:
        arrival = build_arrival_plan(plan, intercity_options, mcp)
        departure = build_return_plan(plan, intercity_options, mcp)
    except GuideDataError as exc:
        return GuideBuildOutcome(missing_inputs=list(exc.missing), notes=[str(exc)])

    context = GuideContext(
        visit_places=[item for item in candidates if isinstance(item, VisitPlaceCandidate)],
        restaurants=[item for item in candidates if isinstance(item, RestaurantCandidate)],
        lodgings=[item for item in candidates if isinstance(item, LodgingCandidate)],
        lodging_areas=[
            item for item in candidates if isinstance(item, LodgingAreaCandidate)
        ],
        evidence=list(evidence),
        intercity_options=list(intercity_options),
        arrival_plan=arrival,
        return_plan=departure,
        preparation_items=list(preparation_items_from_rules(preparation_rules)),
        conflicts=list(conflicts),
        destination_names=dict(destination_names or {}),
        data_snapshot=data_snapshot,
        degraded_items=list(getattr(data_snapshot, "degraded_items", ()) or ()),
        mock_items=list(getattr(data_snapshot, "mock_items", ()) or ()),
        unknown_items=list(getattr(data_snapshot, "unknown_items", ()) or ()),
    )
    try:
        guide = compose_travel_guide(
            plan,
            profile,
            context,
            run_mode=run_mode,
            lifecycle_status=lifecycle_status,
            guide_id=guide_id or f"guide_{uuid.uuid4().hex[:8]}",
            guide_version=guide_version,
            parent_guide_version=parent_guide_version,
        )
    except GuideCompositionError as exc:
        # B6 明确拒绝伪造素材时，我们也如实报缺
        return GuideBuildOutcome(
            missing_inputs=["GUIDE_MATERIAL_MISSING"], notes=[str(exc)]
        )
    return GuideBuildOutcome(guide=guide)


def build_arrival_plan(
    plan: ItineraryPlan,
    intercity_options: Sequence[IntercityOption],
    mcp,
) -> ArrivalPlan:
    """抵达衔接：车站 → 住宿，时长与费用必须来自 Provider 的路线结果。"""

    option = _option_on(intercity_options, plan.start_date)
    if option is None:
        raise GuideDataError(
            f"缺少 {plan.start_date.isoformat()} 的抵达交通方案，无法填出抵达衔接。",
            missing=["ARRIVAL_INTERCITY_MISSING"],
        )
    if not plan.stay_segments:
        raise GuideDataError(
            "计划里没有住宿段，无法确定抵达后先去哪里。", missing=["STAY_SEGMENT_MISSING"]
        )
    lodging_id = plan.stay_segments[0].lodging_id
    route = _single_route(
        mcp, option.destination_station, lodging_id, option.arrival_window.start_at
    )
    return ArrivalPlan(
        station=option.destination_station,
        first_destination_type="LODGING",
        first_destination_id=lodging_id,
        local_transport_mode=_LOCAL_MODE.get(route.mode, "OTHER"),
        duration_minutes=route.duration_minutes,
        estimated_cost=route.estimated_cost,
        reason=f"按 {option.mode} 抵达 {option.destination_station} 后，用 {route.mode} 去住宿。",
    )


def build_return_plan(
    plan: ItineraryPlan,
    intercity_options: Sequence[IntercityOption],
    mcp,
) -> ReturnPlan:
    """返程衔接：住宿 → 车站；最晚出发时间 = 发车时间 − 路上时间 − 缓冲。"""

    option = _option_on(intercity_options, plan.end_date)
    if option is None:
        raise GuideDataError(
            f"缺少 {plan.end_date.isoformat()} 的返程交通方案，无法填出返程衔接。",
            missing=["RETURN_INTERCITY_MISSING"],
        )
    if not plan.stay_segments:
        raise GuideDataError(
            "计划里没有住宿段，无法确定从哪里出发去车站。",
            missing=["STAY_SEGMENT_MISSING"],
        )
    origin_id = plan.stay_segments[0].lodging_id
    route = _single_route(
        mcp, origin_id, option.origin_station, option.departure_window.start_at
    )
    leave_at = option.departure_window.start_at - timedelta(
        minutes=route.duration_minutes + _DEPARTURE_BUFFER_MINUTES
    )
    return ReturnPlan(
        origin_id=origin_id,
        departure_station=option.origin_station,
        local_transport_mode=_LOCAL_MODE.get(route.mode, "OTHER"),
        recommended_leave_at=leave_at,
        duration_minutes=route.duration_minutes,
        estimated_cost=route.estimated_cost,
        reason=(
            f"从 {origin_id} 用 {route.mode} 去 {option.origin_station} 赶 "
            f"{option.departure_window.start_at.time()} 的 {option.mode}，"
            f"并预留 {_DEPARTURE_BUFFER_MINUTES} 分钟缓冲。"
        ),
    )


def preparation_items_from_rules(
    rules: Iterable[PreparationRule],
) -> list[PreparationItem]:
    """把 MCP 的准备规则翻成攻略里的准备事项（trigger_type 映射见下）。"""

    items: list[PreparationItem] = []
    for rule in rules:
        items.append(
            PreparationItem(
                item_id=f"prep_{rule.rule_id}",
                category=rule.category,
                title=rule.item_name,
                description=rule.instruction,
                # PreparationItem 没有 TERRAIN / ALTITUDE，归到 GENERAL
                trigger_type=rule.trigger_type
                if rule.trigger_type in ("WEATHER", "ACTIVITY", "PLACE", "TRAVELER")
                else "GENERAL",
                priority=rule.priority,
                reason=rule.reason,
                trigger_ref=None,
                due_at=rule.due_at,
                evidence_ids=list(rule.evidence_ids),
            )
        )
    return items


def fetch_preparation_rules(
    profile: TripProfile, mcp, *, activity_tags: Sequence[str] = ()
) -> list[PreparationRule]:
    """取准备规则；天气拿不到就不传（不编天气）。"""

    weather_facts = []
    try:
        response = mcp.get_weather(
            GetWeatherRequest(
                date_range=_range(profile), destination_id=None
            )
        )
        weather_facts = list(response.weather_facts)
    except Exception:
        weather_facts = []
    try:
        output = mcp.get_preparation_rules(
            GetPreparationRulesRequest(
                trip_profile=profile,
                activity_tags=list(activity_tags),
                weather_facts=weather_facts,
            )
        )
    except Exception:
        return []
    return list(output.rules)


def store_guide(extras, guide: TravelGuide) -> None:
    """把攻略按版本存进会话（C7 的 GET ?version= 与版本谱系要用）。"""

    kept = [item for item in extras.guides if item.guide_id != guide.guide_id]
    extras.guides = [*kept, guide]
    extras.current_guide_id = guide.guide_id
    extras.current_guide_version = guide.guide_version


def find_guide(
    extras, guide_id: str, version: int | None = None
) -> TravelGuide | None:
    for item in extras.guides:
        if item.guide_id != guide_id:
            continue
        if version is None or item.guide_version == version:
            return item
    return None


# --- 内部工具 ---------------------------------------------------------------


def _option_on(
    options: Sequence[IntercityOption], day
) -> IntercityOption | None:
    for option in options:
        if option.departure_window.start_at.date() == day:
            return option
    return None


def _single_route(mcp, origin: str, destination: str, depart_at: datetime):
    response = mcp.get_route(
        GetRouteRequest(origin=origin, destination=destination, depart_at=depart_at)
    )
    if not response.routes:
        raise GuideDataError(
            f"缺少 {origin} → {destination} 的路线数据，无法填出衔接段的时长与费用。",
            missing=["LOCAL_TRANSFER_ROUTE_MISSING"],
        )
    route = response.routes[0]
    if route.estimated_cost is None:
        raise GuideDataError(
            f"{origin} → {destination} 的路线没有费用数据，衔接段费用无法填写。",
            missing=["LOCAL_TRANSFER_COST_MISSING"],
        )
    return route


def _range(profile: TripProfile):
    from app.schemas import DateRange

    return DateRange(start_date=profile.start_date, end_date=profile.end_date)
