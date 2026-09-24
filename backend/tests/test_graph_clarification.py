"""LangGraph 追问回路的端到端测试（C2 完成判据）。"""

from __future__ import annotations

from datetime import date

from app.graph import PlanStage, build_graph, route_after_missing_check, route_after_retrieve
from app.graph.nodes import NodeDeps
from app.schemas import PlanState, TripProfile
from app.services.destination_recommender import StubDestinationRecommender
from app.services.request_parser import StubTripProfileParser
from app.services.session_store import InMemorySessionRepository
from app.services.travel_mcp_client import FakeTravelMCPClient

REFERENCE = date(2026, 9, 24)


def _deps() -> NodeDeps:
    return NodeDeps(
        parser=StubTripProfileParser(),
        mcp=FakeTravelMCPClient(),
        recommender=StubDestinationRecommender(),
        known_destinations={"成都": "dest_chengdu", "乐山": "dest_leshan"},
        today=lambda: REFERENCE,
    )


def _run(repository: InMemorySessionRepository, session_id: str, text: str):
    from app.graph import run_turn

    graph = build_graph(_deps())
    state = repository.get(session_id)
    new_state, _context = run_turn(graph, state, text)
    repository.save(new_state)
    return new_state


def test_route_after_missing_check_asks_when_fields_missing() -> None:
    state = PlanState(session_id="s", stage=PlanStage.PARSING_REQUEST.value)
    assert route_after_missing_check(state) == "ask_clarification"


def test_route_after_missing_check_retrieves_when_complete() -> None:
    profile = TripProfile(
        session_id="s",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        traveler_count=2,
        budget={"amount": 5000, "currency": "CNY", "flexibility": "NEGOTIABLE"},
        missing_fields=[],
    )
    state = PlanState(
        session_id="s", stage=PlanStage.CHECKING_FIELDS.value, profile=profile
    )
    assert route_after_missing_check(state) == "retrieve_destinations"


def test_route_after_retrieve_handles_insufficient_data() -> None:
    state = PlanState(
        session_id="s", stage=PlanStage.INSUFFICIENT_DATA.value
    )
    assert route_after_retrieve(state) == "report_insufficient_data"
    state = PlanState(session_id="s", stage=PlanStage.RETRIEVING_DESTINATIONS.value)
    assert route_after_retrieve(state) == "recommend_destinations"


def test_first_message_triggers_clarification() -> None:
    repository = InMemorySessionRepository()
    repository.create("sess_1")
    state = _run(repository, "sess_1", "我想出去玩，不想早起")
    assert state.stage == PlanStage.ASKING_CLARIFICATION.value
    assert state.awaiting_user_input is True
    assert state.profile is not None
    assert state.profile.missing_fields
    assert state.destination_candidates == []


def test_clarification_loop_then_recommendation() -> None:
    repository = InMemorySessionRepository()
    repository.create("sess_2")
    _run(repository, "sess_2", "我想出去玩")
    state = _run(
        repository,
        "sess_2",
        "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文",
    )
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value
    assert state.profile is not None and state.profile.missing_fields == []
    assert state.destination_candidates
    for candidate in state.destination_candidates:
        assert candidate.evidence_ids, "推荐必须带证据，不能只有结论"
        assert candidate.coverage_version


def test_unsupported_destination_is_never_recommended() -> None:
    """都江堰数据不足，即使用户点名也不能进入推荐候选。"""

    repository = InMemorySessionRepository()
    repository.create("sess_3")
    state = _run(
        repository,
        "sess_3",
        "从上海出发，10月2号到10月6号，2个人，预算5000元，想去都江堰",
    )
    ids = {c.destination_id for c in state.destination_candidates}
    assert "dest_dujiangyan" not in ids


def test_insufficient_data_when_no_destination_covers_trip() -> None:
    repository = InMemorySessionRepository()
    repository.create("sess_4")
    state = _run(
        repository,
        "sess_4",
        "从上海出发，10月2号到10月31号，2个人，预算50000元",
    )
    assert state.stage == PlanStage.INSUFFICIENT_DATA.value
    assert state.awaiting_user_input is True
    assert state.destination_candidates == []


def test_state_is_validated_after_every_turn() -> None:
    repository = InMemorySessionRepository()
    repository.create("sess_5")
    state = _run(repository, "sess_5", "随便看看")
    assert isinstance(state, PlanState)
