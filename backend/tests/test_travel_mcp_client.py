"""模拟 MCP 客户端行为测试（A 线真实实现的行为基准）。"""

from __future__ import annotations

from datetime import date

from app.schemas import (
    DateRange,
    GetPlaceAvailabilityInput,
    GetRouteInput,
    GetWeatherInput,
    SearchPlanningReadyDestinationsInput,
    SearchTravelKnowledgeInput,
    TravelMode,
)
from app.services.fake_data import DESTINATIONS
from app.services.travel_mcp_client import (
    FakeTravelMCPClient,
    recompute_planning_ready,
)

client = FakeTravelMCPClient()


def _search(query: str = "", duration: int | None = 3):
    return client.search_planning_ready_destinations(
        SearchPlanningReadyDestinationsInput(
            query=query,
            travel_dates=DateRange(
                start_date=date(2026, 10, 2), end_date=date(2026, 10, 6)
            ),
            duration_days=duration,
            traveler_constraints=[],
            top_k=5,
        )
    )


def test_only_planning_ready_destinations_are_returned() -> None:
    ids = {c.destination_id for c in _search().candidates}
    assert "dest_dujiangyan" not in ids, "planning_ready=false 的目的地不得进入候选"
    assert "dest_chengdu" in ids


def test_coverage_is_recomputed_for_longer_trips() -> None:
    """覆盖阈值按天数重算：5 天的行程无法只靠乐山的 9 个地点支撑。"""

    short = {c.destination_id for c in _search(duration=2).candidates}
    long = {c.destination_id for c in _search(duration=5).candidates}
    assert "dest_leshan" in short
    assert "dest_leshan" not in long
    assert "dest_chengdu" in long


def test_no_candidates_for_absurd_duration() -> None:
    assert _search(duration=30).candidates == []


def test_recompute_rule_is_pure_and_testable() -> None:
    coverage = DESTINATIONS[0]["coverage"]
    assert recompute_planning_ready(coverage, None) is True
    assert recompute_planning_ready(coverage, 5) is True
    assert recompute_planning_ready(coverage, 40) is False
    assert recompute_planning_ready(DESTINATIONS[2]["coverage"], 1) is False


def test_knowledge_search_filters_by_destination() -> None:
    output = client.search_travel_knowledge(
        SearchTravelKnowledgeInput(
            query="", destination_ids=["dest_leshan"], top_k=5
        )
    )
    assert [e.evidence_id for e in output.evidence] == ["ev_102"]


def test_knowledge_search_returns_evidence_with_traceable_ids() -> None:
    output = client.search_travel_knowledge(
        SearchTravelKnowledgeInput(query="", destination_ids=["dest_chengdu"], top_k=10)
    )
    assert output.evidence
    for evidence in output.evidence:
        assert evidence.evidence_id
        assert evidence.entity_id
        assert evidence.content


def test_closed_place_reports_unavailable_with_reason() -> None:
    output = client.get_place_availability(
        GetPlaceAvailabilityInput(resource_id="poi_1002", date=date(2026, 10, 3))
    )
    assert output.status.value == "UNAVAILABLE"
    assert output.reason


def test_unknown_resource_is_unknown_not_available() -> None:
    output = client.get_place_availability(
        GetPlaceAvailabilityInput(resource_id="poi_does_not_exist", date=date(2026, 10, 3))
    )
    assert output.status.value == "UNKNOWN"


def test_route_is_deterministic_and_marked_estimated() -> None:
    request = GetRouteInput(origin="poi_1001", destination="poi_1003", mode=TravelMode.METRO)
    first = client.get_route(request)
    second = client.get_route(request)
    assert first == second
    assert first.is_estimated is True
    assert first.source.value == "FAKE"
    assert first.duration_minutes > 0
    assert first.distance_km and first.distance_km > 0


def test_walking_cost_is_zero() -> None:
    output = client.get_route(
        GetRouteInput(origin="poi_1001", destination="poi_1003", mode=TravelMode.WALK)
    )
    assert output.estimated_cost == 0


def test_weather_is_deterministic_and_marked_forecast() -> None:
    request = GetWeatherInput(destination_id="dest_chengdu", date=date(2026, 10, 3))
    assert client.get_weather(request) == client.get_weather(request)
    output = client.get_weather(request)
    assert output.is_forecast is True
    assert output.source.value == "MOCK"
    assert 0 <= (output.precipitation_probability or 0) <= 1
