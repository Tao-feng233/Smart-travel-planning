"""C4 接入 LangGraph 的端到端测试：确认目的地 → 排出行程。

用测试替身 `LodgingAwareMockProvider` 在 A 的 Mock Provider 上补
住宿与路线数据（A 的 Mock 目前没有住宿候选）。
A 的数据到位后，这个替身就可以删掉、直接换成 `V04MockMCPProvider`。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.graph import PlanStage, build_graph, route_after_validation, run_turn
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
    VisitPlaceCandidate,
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


def _extra_indoor() -> VisitPlaceCandidate:
    """室内景点：给 C6 的「下雨换室内」当备用（A 的数据到位后由真实数据提供）。"""
    return VisitPlaceCandidate(
        resource_id="poi_extra_indoor",
        destination_id="dest_chengdu",
        area_id="area_002",
        name="测试室内展馆",
        address="示例地址",
        latitude=30.66,
        longitude=104.07,
        categories=["CULTURE"],
        suggested_duration_minutes=90,
        availability_status="AVAILABLE",
        opening_windows=[
            TimeWindow(
                start_at=datetime.combine(date(2026, 9, 24), time(9, 0), tzinfo=TZ),
                end_at=datetime.combine(date(2026, 9, 24), time(18, 0), tzinfo=TZ),
            )
        ],
        physical_intensity="LOW",
        indoor=True,
        weather_sensitivity="LOW",
        planning_fact_ids=["pf_poi_extra"],
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
        if request.resource_type == "VISIT_PLACE":
            # 多给一个室内景点：C6 的"下雨换室内"需要一个未被当天占用的替代项
            return SearchResourcesResponse(
                resources=[*super().search_resources(request).resources, _extra_indoor()]
            )
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
        previous_plan=extras.current_plan,
        previous_recommendations=extras.last_recommendations,
        run_mode=extras.run_mode,
    )
    repository.save(new_state)
    extras.draft = context.draft
    extras.profile = context.profile
    if context.plan_outcome is not None:
        extras.current_plan = context.validated_plan or context.plan_outcome.plan
        extras.data_snapshot = context.plan_outcome.data_snapshot
        extras.intercity_options = list(context.plan_outcome.intercity_options)
        extras.plan_conflicts = list(context.plan_outcome.conflicts)
    if context.repair_outcome is not None and context.repair_outcome.lineage is not None:
        extras.version_lineage = context.repair_outcome.lineage
    if context.validated_plan is not None:
        extras.current_plan = context.validated_plan
    if context.validation_result is not None:
        extras.plan_conflicts = list(context.validation_result.conflicts)
    if context.recommendations:
        extras.last_recommendations = list(context.recommendations)
    repository.save_extras(session_id, extras)
    return new_state, context


def _session(repository: InMemorySessionRepository, session_id: str) -> None:
    repository.create(session_id)


# --- 修复回路必须有界（B 在真实数据上踩到过无限循环） ----------------------


def test_repair_loop_is_bounded() -> None:
    """验证↔修复之间只允许跑一轮自动修复，且没生成计划时不进修复。"""

    from app.schemas import PlanState

    ready = PlanState(session_id="s", stage=PlanStage.READY.value)
    assert route_after_validation(ready) == "compose_guide"

    insufficient = PlanState(
        session_id="s", stage=PlanStage.INSUFFICIENT_DATA.value
    )
    assert route_after_validation(insufficient) == "finish_turn"

    first_round = PlanState(
        session_id="s", stage=PlanStage.REPAIRING.value, repair_attempts=0
    )
    assert route_after_validation(first_round) == "repair_plan"

    exhausted = PlanState(
        session_id="s", stage=PlanStage.REPAIRING.value, repair_attempts=1
    )
    assert route_after_validation(exhausted) == "finish_turn"


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


def test_confirming_a_system_recommendation_starts_planning() -> None:
    """用户没点名目的地、只回「确认」时也要排程（手动试用时报的缺口）。

    之前只有"用户自己说了想去哪儿 + 确认"能排程；系统推荐 + 确认会原地打转。
    """

    repository = InMemorySessionRepository()
    _session(repository, "sess_pick")
    # 注意：这句里没有"想去成都"
    _run(repository, "sess_pick", "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文")
    state, context = _run(repository, "sess_pick", "确认")
    assert state.stage == PlanStage.READY.value
    assert state.current_plan_id is not None
    assert context.validated_plan is not None


def test_departure_city_is_not_taken_as_destination_pick() -> None:
    """「我从成都出发去大理」不能把**出发地**当成"选了目的地"。

    出发地和目的地用的是同一批城市名，所以采纳逻辑必须先把"出发地表达"排除掉
    （B 实测报过这个误判）。
    """

    repository = InMemorySessionRepository()
    _session(repository, "sess_dep")
    _run(repository, "sess_dep", "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文")
    state, _ = _run(repository, "sess_dep", "我从成都出发去大理")
    assert state.current_plan_id is None, "出发地不该被当成选中的目的地"
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value


def test_naming_destination_again_counts_as_confirmation() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_name")
    _run(repository, "sess_name", TRIP_TEXT)
    state, _ = _run(repository, "sess_name", "就成都")
    assert state.stage == PlanStage.READY.value
    assert state.current_plan_id is not None


def test_rain_incident_replans_only_the_affected_day() -> None:
    """P0 验收：下雨 → 锁定已完成/已预约节点，只重排当天剩余部分。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_rain")
    _run(repository, "sess_rain", TRIP_TEXT)
    first, _ = _run(repository, "sess_rain", "确认")
    assert first.stage == PlanStage.READY.value
    before = repository.get_extras("sess_rain").current_plan
    assert before is not None
    second_day = date(2026, 10, 3)
    day2_before = next(item.node_ids for item in before.days if item.date == second_day)

    state, context = _run(repository, "sess_rain", "今天下雨了")
    assert state.stage == PlanStage.READY.value, "重排后应重新通过验证"
    after = repository.get_extras("sess_rain").current_plan
    assert after is not None
    assert after.plan_version == before.plan_version + 1
    assert after.parent_plan_version == before.plan_version

    # 只动受影响的那天：第二天引用的节点不变
    assert next(item.node_ids for item in after.days if item.date == second_day) == day2_before

    # 当天不再有"室外"景点，换成了室内的备用景点
    by_id = {node.node_id: node for node in after.nodes}
    day_one = next(item for item in after.days if item.date == date(2026, 10, 2))
    resources = {by_id[node_id].resource_id for node_id in day_one.node_ids}
    assert "poi_1003" not in resources
    assert "poi_extra_indoor" in resources

    extras = repository.get_extras("sess_rain")
    assert extras.version_lineage is not None
    assert extras.version_lineage.replacement_relations
    assert extras.version_lineage.new_plan_version == after.plan_version


def test_after_receiving_a_plan_changing_requirements_asks_for_confirmation() -> None:
    """拿到计划后改需求：要再确认一次才重排，不擅自替换用户已经看到的行程。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_after")
    _run(repository, "sess_after", TRIP_TEXT)
    _run(repository, "sess_after", "确认")
    version_before = repository.get_extras("sess_after").current_plan.plan_version

    state, _ = _run(repository, "sess_after", "预算改成8000元")
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert repository.get_extras("sess_after").current_plan.plan_version == version_before


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
    # 只断言"排进了若干景点"，不钉具体是哪一个：
    # 天气参与排序后（A 的对接文档），同分景点谁入选会随数据规模变化
    assert len([item for item in used if item.startswith("poi_")]) >= 3
    assert context.validation_result is not None
    assert context.validation_result.status == "VALID"
    assert not [item for item in context.validation_result.conflicts if item.severity == "ERROR"]
