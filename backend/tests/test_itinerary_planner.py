"""C4 行程生成测试。

用**假 Provider** 提供住宿 / 路线 / 城际数据（A 线的 Mock Provider
目前还没有住宿候选，见 `PROGRESS_REPORT.md` 的缺口清单），
所以这里验证的是排程逻辑本身；A 的数据到位后再做端到端验证。

覆盖三类场景：正常排成计划、C3 禁排日期被尊重、关键数据缺失时明确降级。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.schemas import (
    GetIntercityOptionsRequest,
    GetIntercityOptionsResponse,
    GetResourceAvailabilityResponse,
    GetRouteRequest,
    GetRouteResponse,
    IntercityOption,
    LodgingCandidate,
    Money,
    RestaurantCandidate,
    RouteOption,
    TimeWindow,
    TravelerComposition,
    TripProfile,
    VisitPlaceCandidate,
)
from app.services.availability_filter import filter_candidates_for_trip
from app.services.itinerary_planner import build_itinerary

TZ = timezone(timedelta(hours=8))
START = date(2026, 10, 2)


class FakePlanningProvider:
    """按 (origin, destination) 返回路线；没有的键就代表"数据缺失"。"""

    def __init__(
        self,
        routes: dict[tuple[str, str], list[RouteOption]] | None = None,
        intercity: list[IntercityOption] | None = None,
        with_distance: bool = True,
    ) -> None:
        self._routes = routes or {}
        self._intercity = intercity or []
        self._with_distance = with_distance
        self.route_queries: list[tuple[str, str]] = []

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse:
        self.route_queries.append((request.origin, request.destination))
        options = self._routes.get((request.origin, request.destination), [])
        if options and not self._with_distance:
            options = [item.model_copy(update={"distance_km": None}) for item in options]
        return GetRouteResponse(routes=options)

    def get_intercity_options(
        self, request: GetIntercityOptionsRequest
    ) -> GetIntercityOptionsResponse:
        matched = [
            option
            for option in self._intercity
            if option.arrival_window.start_at.date() == request.arrival_or_departure_date
        ]
        return GetIntercityOptionsResponse(options=matched)


def _route(minutes: int = 20, km: float = 3.0, cost: float = 4.0) -> RouteOption:
    return RouteOption(
        mode="METRO",
        duration_minutes=minutes,
        distance_km=km,
        estimated_cost=Money(amount=cost, currency="CNY"),
        source="MOCK",
        is_estimated=True,
    )


def _intercity(day: date) -> IntercityOption:
    return IntercityOption(
        option_id=f"opt_{day.isoformat()}",
        mode="HIGH_SPEED_RAIL",
        origin_station="上海虹桥",
        destination_station="成都东",
        departure_window=TimeWindow(
            start_at=datetime.combine(day, time(8, 0), tzinfo=TZ),
            end_at=datetime.combine(day, time(8, 30), tzinfo=TZ),
        ),
        arrival_window=TimeWindow(
            start_at=datetime.combine(day, time(11, 0), tzinfo=TZ),
            end_at=datetime.combine(day, time(11, 30), tzinfo=TZ),
        ),
        door_to_door_minutes=210,
        price_range=Money(min_amount=200, max_amount=300, currency="CNY"),
    )


def _profile(days: int = 4, pace: str = "BALANCED", travelers: int = 2) -> TripProfile:
    return TripProfile(
        session_id="sess_plan",
        departure_city="上海",
        start_date=START,
        end_date=START + timedelta(days=days - 1),
        duration_days=days,
        traveler_count=travelers,
        traveler_composition=TravelerComposition(adults=travelers),
        budget=Money(amount=5000),
        budget_flexibility="NEGOTIABLE",
        pace=pace,
        interests=["FOOD", "CULTURE"],
        destination_mode="SINGLE",
    )


def _visit(
    resource_id: str, minutes: int = 120, open_at: tuple[int, int] = (9, 0)
) -> VisitPlaceCandidate:
    start_at = datetime.combine(date(2026, 9, 24), time(*open_at), tzinfo=TZ)
    return VisitPlaceCandidate(
        resource_id=resource_id,
        destination_id="dest_chengdu",
        area_id="area_001",
        name=f"景点 {resource_id}",
        address="示例地址",
        latitude=30.6,
        longitude=104.0,
        categories=["CULTURE"],
        suggested_duration_minutes=minutes,
        availability_status="AVAILABLE",
        opening_windows=[
            TimeWindow(start_at=start_at, end_at=start_at.replace(hour=18, minute=0))
        ],
        physical_intensity="LOW",
        indoor=True,
        weather_sensitivity="LOW",
        planning_fact_ids=[f"pf_{resource_id}"],
        evidence_ids=[f"ev_{resource_id}"],
    )


def _restaurant(resource_id: str = "rest_1") -> RestaurantCandidate:
    open_at = datetime.combine(date(2026, 9, 24), time(11, 0), tzinfo=TZ)
    return RestaurantCandidate(
        resource_id=resource_id,
        destination_id="dest_chengdu",
        area_id="area_001",
        name=f"餐厅 {resource_id}",
        address="示例地址",
        latitude=30.6,
        longitude=104.0,
        cuisine="川菜",
        specialty_dishes=["招牌菜"],
        price_per_person=Money(amount=80, currency="CNY"),
        opening_windows=[TimeWindow(start_at=open_at, end_at=open_at.replace(hour=21))],
        meal_types=["LUNCH", "DINNER"],
        dietary_tags=["辣"],
        route_fit_reason="与景点步行 5 分钟",
        planning_fact_ids=[f"pf_{resource_id}"],
        evidence_ids=[f"ev_{resource_id}"],
    )


def _lodging(resource_id: str = "hotel_1", min_price: float = 300.0) -> LodgingCandidate:
    return LodgingCandidate(
        resource_id=resource_id,
        destination_id="dest_chengdu",
        name=f"酒店 {resource_id}",
        address="示例地址",
        lodging_type="CHAIN",
        lodging_area="示例商圈",
        price_range=Money(min_amount=min_price, max_amount=min_price + 100, currency="CNY"),
        commute_summary="到主要景点地铁 15 分钟",
        availability_status="AVAILABLE",
        planning_fact_ids=[f"pf_{resource_id}"],
        evidence_ids=[f"ev_{resource_id}"],
    )


def _provider(
    *, with_routes: bool = True, with_intercity: bool = True, with_distance: bool = True
) -> FakePlanningProvider:
    routes: dict[tuple[str, str], list[RouteOption]] = {}
    if with_routes:
        for pair in (
            ("poi_1", "rest_1"),
            ("rest_1", "poi_2"),
            ("poi_2", "poi_3"),
            ("poi_3", "rest_1"),
        ):
            routes[pair] = [_route()]
    intercity = [_intercity(START)] if with_intercity else []
    return FakePlanningProvider(
        routes=routes, intercity=intercity, with_distance=with_distance
    )


def _candidates() -> list:
    return [_visit("poi_1"), _visit("poi_2"), _visit("poi_3"), _restaurant(), _lodging()]


def _build(**overrides):
    kwargs = dict(
        profile=_profile(),
        destination_id="dest_chengdu",
        candidates=_candidates(),
        filter_result=None,
        mcp=_provider(),
    )
    kwargs.update(overrides)
    return build_itinerary(**kwargs)


def _day_nodes(plan, index: int):
    by_id = {node.node_id: node for node in plan.nodes}
    return [by_id[node_id] for node_id in plan.days[index].node_ids]


def _availability(resource_id: str, day: date, blocked: dict[str, list[date]]):
    if day in blocked.get(resource_id, []):
        return GetResourceAvailabilityResponse(
            status="UNAVAILABLE", reason=f"{resource_id} 当天闭馆"
        )
    return GetResourceAvailabilityResponse(status="AVAILABLE")


# --- 正常场景 ---------------------------------------------------------------


def test_builds_plan_covering_every_trip_day() -> None:
    outcome = _build()
    assert outcome.plan is not None
    plan = outcome.plan
    assert [day.date for day in plan.days] == [
        START + timedelta(days=offset) for offset in range(4)
    ]
    assert plan.plan_validation_status == "PENDING"  # 验证属于 C5
    assert plan.trip_segments[0].allocated_days == 4


def test_stay_segment_checks_out_the_day_after_the_trip() -> None:
    """与官方 fixture 同一口径：check_out = 行程结束日 + 1。"""

    plan = _build().plan
    assert plan is not None
    stay = plan.stay_segments[0]
    assert stay.check_in_date == START
    assert stay.check_out_date == date(2026, 10, 6)
    assert stay.lodging_id == "hotel_1"
    assert all(day.stay_segment_id == stay.stay_segment_id for day in plan.days)


def test_day_one_starts_with_arrival_and_check_in() -> None:
    plan = _build().plan
    assert plan is not None
    kinds = [node.node_type for node in _day_nodes(plan, 0)]
    assert kinds[0] == "ARRIVAL"
    assert "CHECK_IN" in kinds
    # 抵达时间用 Provider 给的窗口，不是自己估的
    assert _day_nodes(plan, 0)[0].start_at.hour == 11


def test_places_and_meals_are_scheduled() -> None:
    plan = _build().plan
    assert plan is not None
    attractions = [node for node in plan.nodes if node.node_type == "ATTRACTION"]
    meals = [node for node in plan.nodes if node.node_type == "MEAL"]
    assert len(attractions) == 3
    assert meals, "有餐厅数据时应该排出午餐"
    assert all(node.resource_id for node in attractions)


def test_nodes_within_a_day_do_not_overlap() -> None:
    plan = _build().plan
    assert plan is not None
    for index in range(len(plan.days)):
        nodes = sorted(_day_nodes(plan, index), key=lambda item: item.start_at)
        for previous, following in zip(nodes, nodes[1:]):
            assert following.start_at >= previous.end_at


# --- C3 握手：禁排日期必须被尊重 -------------------------------------------


def test_blocked_date_from_step_c3_is_never_scheduled() -> None:
    """C3 说某天闭馆，C4 就不能把该资源排在那天。"""

    visits = [_visit("poi_1"), _visit("poi_2"), _visit("poi_3")]
    blocked = {"poi_1": [START]}
    result = filter_candidates_for_trip(
        visits,
        travel_dates=[START, START + timedelta(days=1)],
        availability_lookup=lambda resource_id, day: _availability(
            resource_id, day, blocked
        ),
    )
    outcome = _build(
        candidates=[*visits, _restaurant(), _lodging()], filter_result=result
    )
    plan = outcome.plan
    assert plan is not None
    assert result.unavailable_dates.get("poi_1") == [START]
    assert "poi_1" not in {node.resource_id for node in _day_nodes(plan, 0)}
    assert "poi_1" in {node.resource_id for node in plan.nodes}


# --- 数据缺失时的降级 -------------------------------------------------------


def test_missing_lodging_reports_insufficient_data() -> None:
    outcome = _build(candidates=[_visit("poi_1"), _restaurant()])
    assert outcome.plan is None
    assert "LODGING_CANDIDATES" in outcome.missing_inputs
    assert outcome.notes


def test_multi_destination_is_out_of_p0_scope() -> None:
    profile = _profile().model_copy(update={"destination_mode": "MULTIPLE"})
    outcome = _build(profile=profile)
    assert outcome.plan is None
    assert outcome.missing_inputs == ["MULTI_DESTINATION_P1"]


def test_missing_route_records_conflict_instead_of_guessing() -> None:
    outcome = _build(mcp=_provider(with_routes=False))
    plan = outcome.plan
    assert plan is not None
    assert plan.travel_legs == []
    assert outcome.conflicts
    assert all(item.type == "DATA_UNKNOWN" for item in outcome.conflicts)
    assert plan.conflict_ids == [item.conflict_id for item in outcome.conflicts]


def test_route_without_distance_is_not_turned_into_a_leg() -> None:
    outcome = _build(mcp=_provider(with_distance=False))
    plan = outcome.plan
    assert plan is not None
    assert plan.travel_legs == []
    assert any("距离" in item.message for item in outcome.conflicts)


def test_ticket_price_is_recorded_as_unknown_not_invented() -> None:
    outcome = _build()
    assert outcome.plan is not None
    assert any(
        item.type == "DATA_UNKNOWN" and "门票" in item.message for item in outcome.conflicts
    )
    assert not [item for item in outcome.plan.cost_items if item.category == "TICKET"]


def test_plan_without_restaurant_still_builds() -> None:
    outcome = _build(candidates=[_visit("poi_1"), _lodging()])
    plan = outcome.plan
    assert plan is not None
    assert [node for node in plan.nodes if node.node_type == "MEAL"] == []


def test_no_intercity_data_only_produces_a_note() -> None:
    outcome = _build(mcp=_provider(with_intercity=False))
    assert outcome.plan is not None
    assert outcome.intercity_options == []
    assert any("城际交通" in note for note in outcome.notes)


# --- 费用与预算 -------------------------------------------------------------


def test_costs_cover_intercity_lodging_and_dining() -> None:
    plan = _build().plan
    assert plan is not None
    categories = {item.category for item in plan.cost_items}
    assert {"INTERCITY", "LODGING", "DINING"} <= categories
    intercity = next(item for item in plan.cost_items if item.category == "INTERCITY")
    assert intercity.pricing_scope == "PER_PERSON"
    assert intercity.quantity == 2
    lodging = next(item for item in plan.cost_items if item.category == "LODGING")
    assert lodging.pricing_scope == "PER_ROOM"
    assert lodging.quantity == 4  # 4 晚 × 1 间（每 2 人 1 间）


def test_budget_summary_is_recomputed_from_cost_items() -> None:
    plan = _build().plan
    assert plan is not None
    estimated = sum(
        (item.unit_price.max_amount or item.unit_price.amount) * item.quantity
        for item in plan.cost_items
        if item.status != "UNKNOWN"
    )
    assert plan.budget_summary.estimated_max_total == estimated
    assert plan.budget_summary.total_limit == 5000
    assert plan.budget_summary.remaining_min == 5000 - estimated


def test_budget_grows_with_traveler_count() -> None:
    two = _build(profile=_profile(travelers=2)).plan
    three = _build(profile=_profile(travelers=3)).plan
    assert two is not None and three is not None
    assert (
        three.budget_summary.estimated_max_total
        > two.budget_summary.estimated_max_total
    )
