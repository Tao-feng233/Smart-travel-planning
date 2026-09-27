"""A-line integration check against C's real planning graph.

The rule-based parser/recommender keep this regression deterministic.  The
test proves that A's actual mock Provider reaches a validated C4/C5 plan
without the lodging or local-route test substitute used by C's own E2E test.
"""

from __future__ import annotations

from datetime import date

from app.graph import NodeDeps, PlanStage, build_graph
from app.schemas import RunMode
from app.services import v04_mock_provider
from app.services.destination_recommender import StubDestinationRecommender
from app.services.request_parser import StubTripProfileParser
from app.services.session_service import SessionService
from app.services.session_store import InMemorySessionRepository
from app.services.v04_mock_provider import V04MockMCPProvider


def test_a_mock_data_reaches_a_validated_plan_without_data_substitute() -> None:
    provider = V04MockMCPProvider()
    deps = NodeDeps(
        parser=StubTripProfileParser(),
        mcp=provider,
        recommender=StubDestinationRecommender(),
        known_destinations=v04_mock_provider.known_destinations(),
        today=lambda: date(2026, 9, 24),
    )
    repository = InMemorySessionRepository()
    service = SessionService(
        repository,
        build_graph(deps),
        known_destinations=deps.known_destinations,
        data_is_mock=True,
        mcp=provider,
    )
    state = service.create_session(session_id="sess_a_mock_flow", run_mode=RunMode.DEMO)

    state, _, _ = service.send_message(
        state.session_id,
        "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，想去成都",
    )
    assert state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value

    state, _, warnings = service.send_message(state.session_id, "确认")
    extras = repository.get_extras(state.session_id)
    plan = extras.current_plan

    assert plan is not None
    assert plan.plan_validation_status == "VALID"
    assert plan.stay_segments
    assert plan.stay_segments[0].lodging_id.startswith("lodging_")
    assert len(plan.days) == 5
    assert not [
        conflict
        for conflict in extras.plan_conflicts
        if conflict.conflict_id.startswith("conflict_route_missing_")
    ]
    assert extras.data_snapshot is not None
    assert extras.data_snapshot.run_mode == RunMode.DEMO
    assert any(item.code == "MOCK_DATA_IN_DEMO" for item in warnings)
