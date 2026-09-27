"""C4 行程生成：把 C3 筛出来的可用资源排成 `ItineraryPlan`。

契约依据：`CONTRACTS.md` §7（TripSegment / StaySegment / PlanNode / TravelLeg /
DayPlan / CostItem / BudgetSummary / ItineraryPlan）。

三条**硬要求**（违反会被契约校验器直接抓住）：

1. **不编数据**：路线、住宿、价格只能来自 MCP Provider；拿不到就记
   `Conflict(type=DATA_UNKNOWN)` 或直接返回"资料不足"，绝不自己估一个数字填进去。
2. **尊重 C3 的结论**：`TripFilterResult.unavailable_dates` 里的日期
   不得安排对应资源（`CONTRACTS.md` §14 不变量 2）。
3. **预算只能由 `CostItem[]` 算**：`BudgetSummary` 在本模块按同一算法复算，
   `ItineraryPlan` 的校验器还会再核对一遍。

本模块只产出 `plan_validation_status = PENDING`：能否算 VALID 属于 C5。

P0 范围的简化（写进 `PROGRESS_REPORT.md`，不是隐藏行为）：

```text
单目的地（多目的地属于 P1，直接返回资料不足）
每天景点数按节奏固定：RELAXED 1 / BALANCED 2 / INTENSE 3
不做区域聚类优化；不按天气重排（自动天气触发器是 P1）
住宿按「每 2 人 1 间」估算房晚；退房日 = 行程结束日 + 1（与官方 fixture 一致）
景点门票没有数据 → 记 DATA_UNKNOWN 冲突，不猜价格、不塞 0 元费用项
ArrivalPlan / ReturnPlan 尚未生成（缺「车站 → 住宿」的路线数据），C7 之前补
```
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable, Protocol, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas import (
    BudgetSummary,
    Conflict,
    CostItem,
    DataSnapshot,
    DayPlan,
    GetIntercityOptionsRequest,
    GetRouteRequest,
    IntercityOption,
    ItineraryPlan,
    LodgingAreaCandidate,
    LodgingCandidate,
    Money,
    PlanNode,
    PlanValidationStatus,
    ResourceCandidateBase,
    RestaurantCandidate,
    RunMode,
    StaySegment,
    TravelLeg,
    TripProfile,
    TripSegment,
    VisitPlaceCandidate,
)
from app.services.availability_filter import TripFilterResult

#: 节奏 → 每天安排的景点数
_PLACES_PER_DAY = {"RELAXED": 1, "BALANCED": 2, "INTENSE": 3}
#: 每天的起步时间（用户说了「不想早起」而写入 `earliest_day_start` 时会被覆盖）
_DEFAULT_DAY_START = time(9, 0)
#: 一顿饭、一次入住、一次抵达各预留多久（分钟）
_MEAL_MINUTES = 60
_CHECK_IN_MINUTES = 30
_ARRIVAL_MINUTES = 30
#: 景点没有时长数据时的兜底游览时长（分钟）
_DEFAULT_VISIT_MINUTES = 120


class PlanningProvider(Protocol):
    """排程需要的 MCP 工具子集（A 线 Provider 已实现）。"""

    def get_route(self, request: GetRouteRequest): ...

    def get_intercity_options(self, request: GetIntercityOptionsRequest): ...


@dataclass
class PlanBuildOutcome:
    """排程结果：要么给出计划，要么说清缺什么（不允许沉默失败）。"""

    plan: ItineraryPlan | None
    conflicts: list[Conflict] = field(default_factory=list)
    #: 缺失的关键输入（例如 `LODGING_CANDIDATES`），用于向用户解释为什么没生成
    missing_inputs: list[str] = field(default_factory=list)
    #: 排程过程中的降级说明
    notes: list[str] = field(default_factory=list)
    #: 本轮取到的城际交通候选（C7 组攻略时要用，存在会话里）
    intercity_options: list[IntercityOption] = field(default_factory=list)
    #: 本计划引用的数据版本（`CONTRACTS.md` §4.4，C7 组攻略时要用）
    data_snapshot: DataSnapshot | None = None


def build_itinerary(
    *,
    profile: TripProfile,
    destination_id: str,
    candidates: Sequence[ResourceCandidateBase],
    filter_result: TripFilterResult | None = None,
    mcp: PlanningProvider,
    run_mode: RunMode = RunMode.DEMO,
    plan_version: int = 1,
    parent_plan_version: int | None = None,
    clock: Callable[[], datetime] | None = None,
) -> PlanBuildOutcome:
    """生成单目的地行程计划；缺关键输入时返回"资料不足"而不是残缺计划。"""

    if profile.destination_mode == "MULTIPLE":
        return PlanBuildOutcome(
            plan=None,
            missing_inputs=["MULTI_DESTINATION_P1"],
            notes=["多目的地规划属于 P1，当前只支持单目的地。"],
        )

    visits = [item for item in candidates if isinstance(item, VisitPlaceCandidate)]
    restaurants = [item for item in candidates if isinstance(item, RestaurantCandidate)]
    lodgings = [item for item in candidates if isinstance(item, LodgingCandidate)]
    areas = [item for item in candidates if isinstance(item, LodgingAreaCandidate)]

    if not lodgings:
        # `ItineraryPlan.stay_segments` 与 `DayPlan.stay_segment_id` 都是必填，
        # 没有住宿候选就产不出合法计划——报缺数据，不用假 ID 顶替。
        return PlanBuildOutcome(
            plan=None,
            missing_inputs=["LODGING_CANDIDATES"],
            notes=["缺少住宿候选数据：没有住宿无法生成含过夜的完整行程。"],
        )

    tz = _resolve_timezone(profile, candidates)
    conflicts: list[Conflict] = []
    notes: list[str] = []

    lodging, stay_segment = _build_stay_segment(profile, lodgings, tz)
    trip_segment = TripSegment(
        segment_id=f"seg_{destination_id}",
        destination_id=destination_id,
        start_date=profile.start_date,
        end_date=profile.end_date,
        allocated_days=profile.duration_days,
    )
    days = _trip_dates(profile)
    blocked = _blocked_dates(filter_result)

    intercity = _fetch_intercity(profile, destination_id, mcp, notes)
    arrival = _arrival_option(intercity, profile.start_date)

    nodes: list[PlanNode] = []
    legs: list[TravelLeg] = []
    leg_costs: list[CostItem] = []
    day_plans: list[DayPlan] = []

    schedule = _assign_places(visits, days, profile.pace, blocked, notes)
    meals_used = 0

    for index, day in enumerate(days):
        day_nodes: list[PlanNode] = []
        day_legs: list[TravelLeg] = []
        slot = _at(day, _day_start(profile), tz)

        if index == 0 and arrival is not None:
            arrive = _make_node(
                node_type="ARRIVAL",
                resource_id=None,
                start=arrival.arrival_window.start_at,
                end=arrival.arrival_window.end_at,
                reason=f"按 Provider 返回的 {arrival.mode} 抵达（{arrival.destination_station}）。",
            )
            nodes.append(arrive)
            day_nodes.append(arrive)
            slot = max(slot, arrive.end_at)

        if index == 0:
            check_in = _make_node(
                node_type="CHECK_IN",
                resource_id=lodging.resource_id,
                start=slot,
                end=slot + timedelta(minutes=_CHECK_IN_MINUTES),
                reason=f"先入住 {lodging.name}（{lodging.lodging_area}），再开始当天行程。",
                evidence_ids=lodging.evidence_ids,
            )
            nodes.append(check_in)
            day_nodes.append(check_in)
            slot = check_in.end_at

        placed = 0
        for place in schedule.get(day, []):
            fitted = _fit_visit(place, day, slot, tz)
            if fitted is None:
                notes.append(
                    f"{day.isoformat()} 的开放时间排不下 {place.name}，已跳过该地点。"
                )
                continue
            node, slot = fitted
            nodes.append(node)
            day_nodes.append(node)
            placed += 1
            if placed == 1 and restaurants and slot.hour < 15:
                meal, slot, used = _append_meal(
                    day, slot, restaurants, tz, nodes
                )
                if meal is not None:
                    day_nodes.append(meal)
                    meals_used += used

        if placed == 0 and index != 0:
            notes.append(f"{day.isoformat()} 没有排到游玩地点。")

        for previous, following in zip(day_nodes, day_nodes[1:]):
            leg, conflict, cost = _build_leg(
                previous, following, mcp, len(legs) + 1, len(leg_costs) + 1
            )
            if leg is not None:
                legs.append(leg)
                day_legs.append(leg)
            if cost is not None:
                leg_costs.append(cost)
            if conflict is not None:
                conflicts.append(conflict)

        day_plans.append(
            DayPlan(
                date=day,
                segment_id=trip_segment.segment_id,
                stay_segment_id=stay_segment.stay_segment_id,
                node_ids=[node.node_id for node in day_nodes],
                travel_leg_ids=[leg.leg_id for leg in day_legs],
            )
        )

    if len(days) > 1:
        notes.append(f"住宿覆盖 {len(days)} 晚：{lodging.lodging_area}（P0 单住宿）。")
    cost_items = collect_costs(
        profile=profile,
        leg_costs=leg_costs,
        stay_lodging=lodging,
        restaurants=restaurants,
        meal_count=meals_used,
        intercity_options=[arrival] if arrival is not None else [],
    )
    if any(node.node_type == "ATTRACTION" for node in nodes):
        conflicts.append(
            Conflict(
                conflict_id="conflict_ticket_price_unknown",
                type="DATA_UNKNOWN",
                severity="WARNING",
                scope="COST",
                message="景点门票价格暂无数据，预算里只含住宿、餐饮与已知交通。",
                status="OPEN",
            )
        )
    if areas:
        notes.append(f"另有 {len(areas)} 个住宿区域候选，备选安排留到 C5/C6。")

    snapshot = _build_snapshot(
        profile=profile,
        run_mode=run_mode,
        candidates=candidates,
        clock=clock,
    )
    plan = ItineraryPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:8]}",
        plan_version=plan_version,
        parent_plan_version=parent_plan_version,
        session_id=profile.session_id,
        timezone=profile.timezone,
        start_date=profile.start_date,
        end_date=profile.end_date,
        trip_segments=[trip_segment],
        stay_segments=[stay_segment],
        days=day_plans,
        nodes=nodes,
        travel_legs=legs,
        cost_items=cost_items,
        budget_summary=_budget_summary(cost_items, profile),
        plan_validation_status=PlanValidationStatus.PENDING,
        conflict_ids=[conflict.conflict_id for conflict in conflicts],
        data_snapshot_id=snapshot.data_snapshot_id,
    )
    return PlanBuildOutcome(
        plan=plan,
        conflicts=conflicts,
        notes=notes,
        intercity_options=intercity,
        data_snapshot=snapshot,
    )


# --- 住宿 -------------------------------------------------------------------


def _build_stay_segment(
    profile: TripProfile, lodgings: Sequence[LodgingCandidate], tz
) -> tuple[LodgingCandidate, StaySegment]:
    """挑主住宿并生成 `StaySegment`（先可用、再便宜、最后按 ID 稳定排序）。"""

    def sort_key(item: LodgingCandidate):
        bounds = _money_bounds(item.price_range) or (float("inf"), float("inf"))
        available = 0 if item.availability_status == "AVAILABLE" else 1
        return (available, bounds[0], item.resource_id)

    lodging = sorted(lodgings, key=sort_key)[0]
    stay = StaySegment(
        stay_segment_id=f"stay_{lodging.resource_id}",
        check_in_date=profile.start_date,
        # 退房日必须晚于入住日；与官方 fixture 一致：行程结束日 + 1
        check_out_date=profile.end_date + timedelta(days=1),
        lodging_id=lodging.resource_id,
        lodging_area=lodging.lodging_area,
    )
    return lodging, stay


# --- 每天排什么 -------------------------------------------------------------


def _assign_places(
    visits: Sequence[VisitPlaceCandidate],
    days: Sequence[date],
    pace: str,
    blocked: dict[str, list[date]],
    notes: list[str],
) -> dict[date, list[VisitPlaceCandidate]]:
    """把景点轮流分到每天，跳过 C3 标记为"当天不可用"的日期。"""

    per_day = _PLACES_PER_DAY.get(pace, 2)
    queue = list(visits)
    schedule: dict[date, list[VisitPlaceCandidate]] = {day: [] for day in days}
    for day in days:
        placed = 0
        scanned = 0
        while queue and placed < per_day and scanned < len(queue):
            candidate = queue.pop(0)
            scanned += 1
            if day in blocked.get(candidate.resource_id, ()):
                queue.append(candidate)  # 今天不能用，留给后面的日期
                continue
            schedule[day].append(candidate)
            placed += 1
        if placed == 0 and queue:
            notes.append(f"{day.isoformat()} 没有可用的游玩地点（当天全被过滤）。")
    if queue:
        notes.append(f"还有 {len(queue)} 个候选地点没排进 {len(days)} 天的行程。")
    return schedule


def _make_node(
    *,
    node_type: str,
    resource_id: str | None,
    start: datetime,
    end: datetime,
    reason: str,
    evidence_ids: Sequence[str] = (),
) -> PlanNode:
    return PlanNode(
        node_id=f"node_{uuid.uuid4().hex[:8]}",
        node_type=node_type,
        resource_id=resource_id,
        start_at=start,
        end_at=end,
        reason=reason,
        evidence_ids=list(evidence_ids),
    )


def _fit_visit(
    candidate: VisitPlaceCandidate, day: date, slot: datetime, tz
) -> tuple[PlanNode, datetime] | None:
    """把景点放进当天时间轴；开放时间排不下就返回 None（跳过并记 note）。"""

    duration = candidate.suggested_duration_minutes or _DEFAULT_VISIT_MINUTES
    start = slot
    note = ""
    if candidate.opening_windows:
        window = candidate.opening_windows[0]
        opens = datetime.combine(day, window.start_at.timetz(), tzinfo=tz)
        closes = datetime.combine(day, window.end_at.timetz(), tzinfo=tz)
        start = max(start, opens)
        if start + timedelta(minutes=duration) > closes:
            return None
        note = f"，开放 {opens.time()}–{closes.time()}"
    node = _make_node(
        node_type="ATTRACTION",
        resource_id=candidate.resource_id,
        start=start,
        end=start + timedelta(minutes=duration),
        reason=f"安排 {candidate.name}（建议 {duration} 分钟{note}）。",
        evidence_ids=candidate.evidence_ids,
    )
    return node, node.end_at


def _append_meal(
    day: date,
    slot: datetime,
    restaurants: Sequence[RestaurantCandidate],
    tz,
    nodes: list[PlanNode],
) -> tuple[PlanNode | None, datetime, int]:
    """挑一家能覆盖午餐时段的餐厅；一家都排不下就不排（不编餐厅）。"""

    for restaurant in restaurants:
        start = slot
        if restaurant.opening_windows:
            window = restaurant.opening_windows[0]
            opens = datetime.combine(day, window.start_at.timetz(), tzinfo=tz)
            closes = datetime.combine(day, window.end_at.timetz(), tzinfo=tz)
            start = max(start, opens)
            if start + timedelta(minutes=_MEAL_MINUTES) > closes:
                continue
        node = _make_node(
            node_type="MEAL",
            resource_id=restaurant.resource_id,
            start=start,
            end=start + timedelta(minutes=_MEAL_MINUTES),
            reason=f"午餐安排在 {restaurant.name}（{restaurant.cuisine}）。",
            evidence_ids=restaurant.evidence_ids,
        )
        nodes.append(node)
        return node, node.end_at, 1
    return None, slot, 0


def _build_leg(
    previous: PlanNode,
    following: PlanNode,
    mcp: PlanningProvider,
    leg_sequence: int,
    cost_sequence: int,
) -> tuple[TravelLeg | None, Conflict | None, CostItem | None]:
    """两点之间的交通；Provider 没数据时返回冲突，绝不估时间。"""

    if previous.resource_id is None or following.resource_id is None:
        return None, None, None
    response = mcp.get_route(
        GetRouteRequest(
            origin=previous.resource_id,
            destination=following.resource_id,
            depart_at=previous.end_at,
        )
    )
    if not response.routes:
        return (
            None,
            Conflict(
                conflict_id=f"conflict_route_missing_{leg_sequence:03d}",
                type="DATA_UNKNOWN",
                severity="WARNING",
                scope="TRAVEL_LEG",
                message=(
                    f"缺少 {previous.resource_id} → {following.resource_id} 的路线数据，"
                    "这段移动时间未知。"
                ),
                affected_node_ids=[previous.node_id, following.node_id],
                status="OPEN",
            ),
            None,
        )

    route = response.routes[0]
    if route.distance_km is None:
        # 契约要求 `TravelLeg.distance_km` 必填，没距离就宁可不给这一段
        return (
            None,
            Conflict(
                conflict_id=f"conflict_route_incomplete_{leg_sequence:03d}",
                type="DATA_UNKNOWN",
                severity="WARNING",
                scope="TRAVEL_LEG",
                message=f"{previous.resource_id} → {following.resource_id} 缺少距离数据。",
                affected_node_ids=[previous.node_id, following.node_id],
                status="OPEN",
            ),
            None,
        )

    depart = previous.end_at
    leg = TravelLeg(
        leg_id=f"leg_{leg_sequence:03d}",
        from_node_id=previous.node_id,
        to_node_id=following.node_id,
        recommended_mode=route.mode,
        depart_at=depart,
        arrive_at=depart + timedelta(minutes=route.duration_minutes),
        duration_minutes=route.duration_minutes,
        distance_km=route.distance_km,
        reason=f"使用 Provider 返回的 {route.mode} 方案（来源 {route.source}）。",
        source="FAKE" if route.source == "MOCK" else "MAP_PROVIDER",
        is_estimated=route.is_estimated,
        transfer_count=route.transfer_count or 0,
    )
    cost = None
    if route.estimated_cost is not None:
        cost = CostItem(
            cost_item_id=f"cost_{cost_sequence:03d}",
            category="LOCAL_TRANSPORT",
            item_ref=leg.leg_id,
            unit_price=route.estimated_cost,
            quantity=1,
            pricing_scope="PER_GROUP",
            status="ESTIMATED",
        )
    return leg, None, cost


# --- 城际交通与费用 ---------------------------------------------------------


def _fetch_intercity(
    profile: TripProfile,
    destination_id: str,
    mcp: PlanningProvider,
    notes: list[str],
) -> list[IntercityOption]:
    """取去程与返程的城际候选；Provider 没有数据时只记 note，不编班次。"""

    collected: list[IntercityOption] = []
    for moment, label in ((profile.start_date, "去程"), (profile.end_date, "返程")):
        try:
            response = mcp.get_intercity_options(
                GetIntercityOptionsRequest(
                    origin_city=profile.departure_city,
                    destination_id=destination_id,
                    arrival_or_departure_date=moment,
                )
            )
        except Exception as exc:  # Provider 未实现 / 数据缺失：降级但不崩
            notes.append(f"{label}城际交通查询失败（{type(exc).__name__}），已跳过。")
            continue
        if not response.options:
            notes.append(f"{label}（{moment.isoformat()}）城际交通暂无数据。")
            continue
        collected.extend(response.options)
    return collected


def _arrival_option(
    options: Sequence[IntercityOption], first_day: date
) -> IntercityOption | None:
    for option in options:
        if option.arrival_window.start_at.date() == first_day:
            return option
    return None


def _intercity_cost(
    option: IntercityOption, profile: TripProfile, sequence: int
) -> CostItem | None:
    if _money_bounds(option.price_range) is None:
        return None
    return CostItem(
        cost_item_id=f"cost_{sequence:03d}",
        category="INTERCITY",
        item_ref=option.option_id,
        unit_price=option.price_range,
        quantity=profile.traveler_count,
        pricing_scope="PER_PERSON",
        status="ESTIMATED",
        evidence_ids=list(option.evidence_ids),
    )


def _lodging_cost(
    lodging: LodgingCandidate, profile: TripProfile, sequence: int
) -> CostItem | None:
    if _money_bounds(lodging.price_range) is None:
        return None
    nights = max(1, (profile.end_date - profile.start_date).days + 1)
    return CostItem(
        cost_item_id=f"cost_{sequence:03d}",
        category="LODGING",
        item_ref=lodging.resource_id,
        unit_price=lodging.price_range,
        quantity=nights * _rooms(profile.traveler_count),
        pricing_scope="PER_ROOM",
        status="ESTIMATED",
        evidence_ids=list(lodging.evidence_ids),
    )


def _dining_cost(
    restaurants: Sequence[RestaurantCandidate],
    meals_used: int,
    profile: TripProfile,
    sequence: int,
) -> CostItem | None:
    if meals_used == 0 or not restaurants:
        return None
    restaurant = restaurants[0]
    if _money_bounds(restaurant.price_per_person) is None:
        return None
    return CostItem(
        cost_item_id=f"cost_{sequence:03d}",
        category="DINING",
        item_ref=restaurant.resource_id,
        unit_price=restaurant.price_per_person,
        quantity=profile.traveler_count * meals_used,
        pricing_scope="PER_PERSON",
        status="ESTIMATED",
        evidence_ids=list(restaurant.evidence_ids),
    )


def _budget_summary(
    cost_items: Sequence[CostItem], profile: TripProfile
) -> BudgetSummary:
    """按 `ItineraryPlan` 校验器的同一算法复算预算（否则模型会直接拒绝）。"""

    known_total = 0.0
    estimated_min = 0.0
    estimated_max = 0.0
    unknown_ids: list[str] = []
    by_category: dict[str, float] = {}

    for item in cost_items:
        money = item.unit_price
        if item.status == "UNKNOWN":
            unknown_ids.append(item.cost_item_id)
            continue
        if money.amount is not None:
            minimum = maximum = float(money.amount) * item.quantity
        else:
            minimum = float(money.min_amount) * item.quantity
            maximum = float(money.max_amount) * item.quantity
        if item.status == "KNOWN":
            known_total += minimum
        else:
            estimated_min += minimum
            estimated_max += maximum
        by_category[item.category] = by_category.get(item.category, 0.0) + minimum

    limit_bounds = _money_bounds(profile.budget)
    total_limit = limit_bounds[1] if limit_bounds else 0.0
    calculated_min = known_total + estimated_min
    calculated_max = known_total + estimated_max
    return BudgetSummary(
        currency=profile.budget.currency,
        total_limit=total_limit,
        known_total=known_total,
        estimated_min_total=calculated_min,
        estimated_max_total=calculated_max,
        remaining_min=total_limit - calculated_max,
        remaining_max=total_limit - calculated_min,
        by_category=by_category,
        unknown_cost_item_ids=unknown_ids,
    )


def collect_costs(
    *,
    profile: TripProfile,
    leg_costs: Sequence[CostItem],
    stay_lodging: LodgingCandidate | None,
    restaurants: Sequence[RestaurantCandidate],
    meal_count: int,
    intercity_options: Sequence[IntercityOption],
) -> list[CostItem]:
    """按统一规则汇总费用项，并统一重排 `cost_item_id`。

    C4（首次排程）与 C6（修复后重算）共用这一处，避免两条线各自算一套预算。
    """

    items: list[CostItem] = []
    for option in intercity_options:
        cost = _intercity_cost(option, profile, 1)
        if cost is not None:
            items.append(cost)
    if stay_lodging is not None:
        cost = _lodging_cost(stay_lodging, profile, 1)
        if cost is not None:
            items.append(cost)
    dining = _dining_cost(restaurants, meal_count, profile, 1)
    if dining is not None:
        items.append(dining)
    items.extend(leg_costs)
    return [
        item.model_copy(update={"cost_item_id": f"cost_{index:03d}"})
        for index, item in enumerate(items, 1)
    ]


#: C6 修复引擎复用这几个原语（同一套算法，不另写一份）
make_plan_node = _make_node
build_travel_leg = _build_leg
summarize_budget = _budget_summary
arrival_option_for = _arrival_option
fetch_intercity_options = _fetch_intercity


# --- 辅助 -------------------------------------------------------------------


def _trip_dates(profile: TripProfile) -> list[date]:
    span = (profile.end_date - profile.start_date).days
    return [profile.start_date + timedelta(days=offset) for offset in range(span + 1)]


def _day_start(profile: TripProfile) -> time:
    if profile.earliest_day_start:
        try:
            hour, minute = profile.earliest_day_start.split(":")
            return time(int(hour), int(minute))
        except ValueError:  # 契约没规定格式，格式不对就回退默认
            return _DEFAULT_DAY_START
    return _DEFAULT_DAY_START


def _at(day: date, moment: time, tz) -> datetime:
    return datetime.combine(day, moment, tzinfo=tz)


def _resolve_timezone(profile: TripProfile, candidates: Sequence[ResourceCandidateBase]):
    """优先用数据自带的时区，其次 profile.timezone，最后本机时区。"""

    for item in candidates:
        windows = getattr(item, "opening_windows", None)
        if windows:
            return windows[0].start_at.tzinfo
    try:
        return ZoneInfo(profile.timezone)
    except (ZoneInfoNotFoundError, ValueError):  # pragma: no cover - 依赖系统 tzdata
        return datetime.now().astimezone().tzinfo


def _blocked_dates(filter_result: TripFilterResult | None) -> dict[str, list[date]]:
    return dict(filter_result.unavailable_dates) if filter_result else {}


def _money_bounds(money: Money | None) -> tuple[float, float] | None:
    if money is None:
        return None
    if money.amount is not None:
        return (float(money.amount), float(money.amount))
    if money.min_amount is not None and money.max_amount is not None:
        return (float(money.min_amount), float(money.max_amount))
    return None


def _rooms(traveler_count: int) -> int:
    """P0 假设：每 2 人 1 间房（已写进 `PROGRESS_REPORT.md` 的简化清单）。"""

    return max(1, math.ceil(traveler_count / 2))


def _build_snapshot(
    *,
    profile: TripProfile,
    run_mode: RunMode,
    candidates: Sequence[ResourceCandidateBase],
    clock: Callable[[], datetime] | None,
) -> DataSnapshot:
    evidence_ids = sorted({eid for item in candidates for eid in item.evidence_ids})
    fact_ids = sorted({fid for item in candidates for fid in item.planning_fact_ids})
    return DataSnapshot(
        data_snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
        created_at=(clock or (lambda: datetime.now().astimezone()))(),
        run_mode=run_mode,
        trip_profile_version=profile.profile_version,
        readiness_evaluation_ids=[],
        planning_fact_ids=fact_ids,
        evidence_ids=evidence_ids,
        provider_versions=["v04-mock-provider"],
        ruleset_versions=["rules-2026-09-24-v1"],
        expired_items=[],
        degraded_items=[],
        # 当前全部数据来自 Mock，必须显式登记（§14 不变量 5）
        mock_items=[*evidence_ids, *fact_ids],
        unknown_items=["TICKET_PRICE", "REALTIME_HOTEL_AVAILABILITY"],
    )
