"""LangGraph 追问 + 推荐 + C3 前置过滤回路的端到端测试。"""

from __future__ import annotations

from datetime import date

from app.graph import (
    PlanStage,
    build_graph,
    route_after_fetch,
    route_after_missing_check,
    route_after_retrieve,
    run_turn,
)
from app.graph.nodes import NodeDeps
from app.schemas import PlanState, RunMode
from app.services import v04_mock_provider
from app.services.destination_recommender import StubDestinationRecommender
from app.services.request_parser import StubTripProfileParser
from app.services.session_store import InMemorySessionRepository
from app.services.v04_mock_provider import V04MockMCPProvider

REFERENCE = date(2026, 9, 24)
TRIP_TEXT = "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文"


def _deps() -> NodeDeps:
    return NodeDeps(
        parser=StubTripProfileParser(),
        mcp=V04MockMCPProvider(),
        recommender=StubDestinationRecommender(),
        known_destinations=v04_mock_provider.known_destinations(),
        today=lambda: REFERENCE,
    )


def _run(repository: InMemorySessionRepository, session_id: str, text: str):
    """推进一轮，并像 SessionService 一样把 Draft / Profile 存回会话。"""

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
    repository.save_extras(session_id, extras)
    return new_state, context


def _session(repository: InMemorySessionRepository, session_id: str) -> None:
    repository.create(session_id, RunMode.DEMO)


# --- 条件边（纯函数，可单独测试） -------------------------------------------


def test_route_after_missing_check_asks_when_fields_missing() -> None:
    state = PlanState(session_id="s", stage=PlanStage.CHECKING_FIELDS.value)
    state.awaiting_user_input = True
    assert route_after_missing_check(state) == "ask_clarification"


def test_route_after_missing_check_retrieves_when_complete() -> None:
    state = PlanState(session_id="s", stage=PlanStage.CHECKING_FIELDS.value)
    assert state.awaiting_user_input is False
    assert route_after_missing_check(state) == "retrieve_destinations"


def test_route_after_retrieve_handles_insufficient_data() -> None:
    insufficient = PlanState(
        session_id="s", stage=PlanStage.INSUFFICIENT_DATA.value
    )
    assert route_after_retrieve(insufficient) == "report_insufficient_data"
    ok = PlanState(session_id="s", stage=PlanStage.RETRIEVING_DESTINATIONS.value)
    assert route_after_retrieve(ok) == "recommend_destinations"


def test_route_after_fetch_only_filters_when_resources_were_fetched() -> None:
    waiting = PlanState(
        session_id="s", stage=PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    )
    assert route_after_fetch(waiting) == "finish_turn"
    fetching = PlanState(session_id="s", stage=PlanStage.FILTERING_RESOURCES.value)
    assert route_after_fetch(fetching) == "filter_availability"


# --- 端到端回路 -------------------------------------------------------------


def test_first_message_triggers_clarification() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_1")
    state, _ = _run(repository, "sess_1", "我想出去玩，不想早起")
    assert state.stage == PlanStage.ASKING_CLARIFICATION.value
    assert state.awaiting_user_input is True
    # 关键字段未补齐：不生成正式 TripProfile，缺失信息保存在会话的 Draft 里
    assert state.trip_profile_version == 0
    draft = repository.get_extras("sess_1").draft
    assert draft is not None
    assert draft.compute_missing_fields() == [
        "departure_city",
        "start_date",
        "end_date",
        "traveler_count",
        "budget",
    ]
    assert state.destination_candidate_ids == []


def test_clarification_loop_then_recommendation() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_2")
    _run(repository, "sess_2", "我想出去玩")
    state, context = _run(repository, "sess_2", TRIP_TEXT)
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert state.trip_profile_version == 1
    assert repository.get_extras("sess_2").profile is not None
    assert state.destination_candidate_ids
    assert context.recommendations
    for candidate in context.recommendations:
        assert candidate.evidence_ids, "推荐必须带证据，不能只有结论"
        assert candidate.readiness_id


def test_profile_version_bumps_when_requirements_change() -> None:
    """需求变了就是新版本（`CONTRACTS.md` §14 不变量 7）。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_bump")
    first, _ = _run(repository, "sess_bump", TRIP_TEXT)
    assert first.trip_profile_version == 1
    second, _ = _run(repository, "sess_bump", "预算改成8000元")
    assert second.trip_profile_version == 2


def test_unsupported_destination_is_never_recommended() -> None:
    """都江堰数据不足，即使用户点名也不能进入推荐候选。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_3")
    state, _ = _run(repository, "sess_3", TRIP_TEXT + "，想去都江堰")
    assert "dest_dujiangyan" not in state.destination_candidate_ids


def test_insufficient_data_when_no_destination_covers_trip() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_4")
    state, _ = _run(
        repository,
        "sess_4",
        "从上海出发，10月2号到10月31号，2个人，预算50000元",
    )
    assert state.stage == PlanStage.INSUFFICIENT_DATA.value
    assert state.awaiting_user_input is True
    assert state.destination_candidate_ids == []


def test_named_destination_triggers_resource_prefilter() -> None:
    """C3 接入点：用户点名目的地后，规划前先把不可用资源挡掉。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_5")
    state, context = _run(repository, "sess_5", TRIP_TEXT + "，想去成都")
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert context.filter_result is not None
    excluded = [item.resource_id for item in context.filter_result.excluded]
    assert "poi_1002" in excluded, "行程期内一直闭馆的资源必须被排除"
    assert "poi_1002" not in state.resource_candidate_ids
    assert state.resource_candidate_ids
    assert all(
        item.reason for item in context.filter_result.excluded
    ), "排除原因不得为空（不允许静默丢弃）"


def test_all_resources_excluded_reports_insufficient_data() -> None:
    """候选全部不可用时不得硬凑计划，必须明确报资料不足。"""

    repository = InMemorySessionRepository()
    _session(repository, "sess_6")
    state, context = _run(
        repository,
        "sess_6",
        "从上海出发，10月2号到10月6号，2个人，预算5000元，想去都江堰",
    )
    # 都江堰知识覆盖不达标 → 连目的地候选都没有
    assert state.destination_candidate_ids == []
    assert state.stage == PlanStage.INSUFFICIENT_DATA.value
    assert context.filter_result is None


def test_state_is_validated_after_every_turn() -> None:
    repository = InMemorySessionRepository()
    _session(repository, "sess_7")
    state, _ = _run(repository, "sess_7", "随便看看")
    assert isinstance(state, PlanState)
