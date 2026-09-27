"""C4 接入 LangGraph 的端到端测试：确认目的地 → 排出行程。

用测试替身 `LodgingAwareMockProvider` 在 A 的 Mock Provider 上补
住宿与路线数据（A 的 Mock 目前没有住宿候选）。
A 的数据到位后，这个替身就可以删掉、直接换成 `V04MockMCPProvider`。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.graph import PlanStage, build_graph, run_turn
from app.graph.nodes import NodeDeps
from app.schemas import (
    GetIntercityOptionsResponse,
    GetRouteResponse,
    IntercityOption,
    LodgingCandidate,
    Money,
    RouteOption,
    SearchResourcesResponse,
    TimeWindow,
    LodgingAreaCandidate,
)
from app.services import v04_mock_provider
from app.services.destination_recommender import StubDestinationRecommender
from app.services.request_parser import StubTripProfileParser
from app.services.session_store import InMemorySessionRepository
from app.services.v04_mock_provider import V04MockMCPProvider

REFERENCE = date(2026, 9, 24)
TZ = timezone(timedelta(hours=8))
TRIP_TEXT = "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，想去成都"


def _lodging() -> LodgingCandidate:
    return LodgingCandidate(
        resource_id="hotel_test_1",
        destination_id="dest_chengdu",
        name="测试酒店",
        address="示例地址",
        lodging_type="CHAIN",
        lodging_area="示例商圈",
        price_range=Money(min_amount=300, max_amount=400, currency="CNY"),
        commute_summary="到主要景点地铁 15 分钟",
        availability_status="AVAILABLE",
        planning_fact_ids=["pf_hotel_test_1"],
        evidence_ids=["ev_301"],
    )


def _lodging_area() -> LodgingAreaCandidate:
    return LodgingAreaCandidate(
        resource_id="area_test_1",
        destination_id="dest_chengdu",
        name="示例住宿区域",
        area_type="CITY_CENTER",
        nearby_transport=["METRO"],
        food_convenience="HIGH",
        planning_fact_ids=["pf_area_test_1"],
        evidence_ids=["ev_301"],
    )


class LodgingAwareMockProvider(V04MockMCPProvider):
    """测试替身：补上住宿候选与"任意两点都有路线"的行为。"""

    def search_resources(self, request):
        if request.resource_type == "LODGING":
            return SearchResourcesResponse(resources=[_lodging()])
        if request.resource_type == "LODGING_AREA":
            return SearchResourcesResponse(resources=[_lodging_area()])
        return super().search_resources(request)

    def get_route(self, request):
        response = super().get_route(request)
        if response.routes:
            return response
        return GetRouteResponse(
            routes=[
                RouteOption(
                    mode="METRO",
                    duration_minutes=15,
                    distance_km=2.5,
                    estimated_cost=Money(amount=4, currency="CNY"),
                    source="MOCK",
                    is_estimated=True,
                )
            ]
        )

    def get_intercity_options(self, request):
        response = super().get_intercity_options(request)
        if response.options:
            return response
        day = request.arrival_or_departure_date
        return GetIntercityOptionsResponse(
            options=[
                IntercityOption(
                    option_id=f"opt_test_{day.isoformat()}",
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
            ]
        )


def _deps() -> NodeDeps:
    return NodeDeps(
        parser=StubTripProfileParser(),
        mcp=LodgingAwareMockProvider(),
        recommender=StubDestinationRecommender(),
        known_destinations=v04_mock_provider.known_destinations(),
        today=lambda: REFERENCE,
    )


def _run(repository: InMemorySessionRepository, session_id: str, text: str):
    graph = build_graph(_deps())
    state = repository.get(session_id)
    extras = repository.get_extras(session_id)
    new_state, context = run_turn(
        graph,
        state,
        text,
        draft=extras.draft,
        profile=extras.profile,
        run_mode=extras.run_mode,
    )
    repository.save(new_state)
    extras.draft = context.draft
    extras.profile = context.profile
    if context.plan_outcome is not None:
        extras.current_plan = context.plan_outcome.plan
        extras.data_snapshot = context.plan_outcome.data_snapshot
        extras.intercity_options = list(context.plan_outcome.intercity_options)
        extras.plan_conflicts = list(context.plan_outcome.conflicts)
    repository.save_extras(session_id, extras)
    return new_state, context


def _session(repository: InMemorySessionRepository, session_id: str) -> None:
    repository.create(session_id)


def test_confirmation_turn_builds_the_itinerary() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_plan")

    first, _ = _run(repository, "sess_plan", TRIP_TEXT)
    assert first.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert first.current_plan_id is None, "确认之前不应生成计划"
    assert repository.get_extras("sess_plan").current_plan is None

    second, context = _run(repository, "sess_plan", "确认")
    # C5 验证紧跟 C4 排程：验证通过 → READY
    assert second.stage == PlanStage.READY.value
    assert second.current_plan_id is not None
    assert second.current_plan_version == 1
    assert second.data_snapshot_id is not None
    assert context.validated_plan is not None
    assert context.validated_plan.plan_validation_status == "VALID"
    assert context.validation_result is not None

    plan = context.plan_outcome.plan
    assert plan is not None
    assert [day.date for day in plan.days] == [
        date(2026, 10, 2) + timedelta(days=offset) for offset in range(5)
    ]
    assert plan.stay_segments[0].lodging_id == "hotel_test_1"
    assert second.conflict_ids == [item.conflict_id for item in context.plan_outcome.conflicts]


def test_plan_is_persisted_for_later_steps() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_store")
    _run(repository, "sess_store", TRIP_TEXT)
    _run(repository, "sess_store", "确认")

    extras = repository.get_extras("sess_store")
    assert extras.current_plan is not None
    assert extras.data_snapshot is not None
    assert extras.intercity_options, "城际候选要留给 C7 组攻略用"
    assert extras.current_plan.budget_summary.total_limit == 5000


def test_non_confirmation_turn_does_not_plan() -> None:
    """改需求但没说确认 → 继续等确认，不擅自排行程。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_wait")
    _run(repository, "sess_wait", TRIP_TEXT)
    state, _ = _run(repository, "sess_wait", "预算改成8000元")
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert state.current_plan_id is None


def test_naming_destination_again_counts_as_confirmation() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_name")
    _run(repository, "sess_name", TRIP_TEXT)
    state, _ = _run(repository, "sess_name", "就成都")
    assert state.stage == PlanStage.READY.value
    assert state.current_plan_id is not None


def test_closed_resource_from_step_c3_never_enters_the_plan() -> None:
    """回归：C3 排除的闭馆资源（poi_1002）绝不能出现在 C4 的计划里。

    这个缺陷是 C5 验证器第一次跑起来时抓到的：C4 当时拿到的是**未过滤**的原始候选，
    于是把行程期内一直闭馆的 poi_1002 排进了计划。根因修复在 `plan_itinerary`，
    验证器是这道防线的兜底。
    """

    repository = InMemorySessionRepository()
    _session(repository, "sess_closed")
    _run(repository, "sess_closed", TRIP_TEXT)
    _, context = _run(repository, "sess_closed", "确认")

    plan = context.validated_plan
    assert plan is not None
    used = {node.resource_id for node in plan.nodes if node.resource_id}
    assert "poi_1002" not in used, "闭馆资源不得进入计划（§14 不变量 2）"
    assert "poi_1001" in used
    assert context.validation_result is not None
    assert context.validation_result.status == "VALID"
    assert not [item for item in context.validation_result.conflicts if item.severity == "ERROR"]
