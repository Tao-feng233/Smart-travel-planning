"""v0.4 模拟 Provider 行为测试（A 线真实 MCP Server 的行为基准）。

模拟数据必须：只返回覆盖达标的目的地、所有结果都能回指到 ID、
不可用资源必须带原因、路线与天气必须标记为估算/预报。
"""

from __future__ import annotations

from datetime import date, timedelta

from app.schemas import (
    DateRange,
    GetIntercityOptionsRequest,
    GetPreparationRulesRequest,
    GetResourceAvailabilityRequest,
    GetResourceFactsRequest,
    GetRouteRequest,
    GetWeatherRequest,
    Money,
    SearchPlanningReadyDestinationsRequest,
    SearchResourcesRequest,
    SearchTravelKnowledgeRequest,
    TravelerComposition,
    TripProfile,
)
from app.services.v04_mock_provider import DataMissingError, V04MockMCPProvider

client = V04MockMCPProvider()


def _profile(days: int = 5, start: date = date(2026, 10, 2)) -> TripProfile:
    return TripProfile(
        session_id="sess_test",
        departure_city="上海",
        start_date=start,
        end_date=start + timedelta(days=days - 1),
        duration_days=days,
        traveler_count=2,
        traveler_composition=TravelerComposition(adults=2),
        budget=Money(amount=5000),
        budget_flexibility="NEGOTIABLE",
        pace="BALANCED",
        interests=["FOOD"],
        destination_mode="UNKNOWN",
    )


def _search(days: int = 5):
    return client.search_planning_ready_destinations(
        SearchPlanningReadyDestinationsRequest(trip_profile=_profile(days), top_k=5)
    )


def test_only_planning_ready_destinations_are_returned() -> None:
    ids = {item.destination_id for item in _search().recommendations}
    assert "dest_dujiangyan" not in ids, "planning_ready=false 的目的地不得进入候选"
    assert "dest_chengdu" in ids


def test_coverage_is_recomputed_for_longer_trips() -> None:
    """覆盖阈值按天数重算：5 天的行程无法只靠乐山的 6 个地点支撑。"""

    short = {item.destination_id for item in _search(days=2).recommendations}
    long = {item.destination_id for item in _search(days=5).recommendations}
    assert "dest_leshan" in short
    assert "dest_leshan" not in long
    assert "dest_chengdu" in long


def test_readiness_evaluation_is_always_returned() -> None:
    """即使没有推荐，也要返回就绪度评估，便于前端解释"为什么没有"。"""

    output = _search(days=30)
    assert output.recommendations == []
    assert output.readiness_evaluations
    assert all(item.planning_ready is False for item in output.readiness_evaluations)
    assert all(item.failed_requirements for item in output.readiness_evaluations)


def test_recommendation_carries_readiness_and_reason() -> None:
    item = _search(days=3).recommendations[0]
    assert item.readiness_id
    assert item.suggested_days >= 1
    assert item.reason


def test_resource_search_returns_contract_candidates() -> None:
    output = client.search_resources(
        SearchResourcesRequest(
            resource_type="VISIT_PLACE",
            destination_id="dest_chengdu",
            date_range=DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 6)),
        )
    )
    assert output.resources
    for item in output.resources:
        assert item.resource_id
        assert item.destination_id == "dest_chengdu"
        assert item.resource_type == "VISIT_PLACE"


def test_all_mock_candidate_planning_facts_are_resolvable() -> None:
    date_range = DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 4))
    resources = []
    for resource_type in ("VISIT_PLACE", "RESTAURANT"):
        resources.extend(
            client.search_resources(
                SearchResourcesRequest(
                    resource_type=resource_type,
                    destination_id="dest_chengdu",
                    date_range=date_range,
                )
            ).resources
        )
    response = client.get_resource_facts(
        GetResourceFactsRequest(
            resource_ids=[item.resource_id for item in resources],
            date_range=date_range,
        )
    )
    available = {item.planning_fact_id for item in response.planning_facts}
    referenced = {
        fact_id for item in resources for fact_id in item.planning_fact_ids
    }
    assert referenced.issubset(available)


def test_closed_place_reports_unavailable_with_reason() -> None:
    output = client.get_resource_availability(
        GetResourceAvailabilityRequest(resource_id="poi_1002", date=date(2026, 10, 3))
    )
    assert output.status == "UNAVAILABLE"
    assert output.reason


def test_unknown_resource_is_unknown_not_available() -> None:
    output = client.get_resource_availability(
        GetResourceAvailabilityRequest(
            resource_id="poi_does_not_exist", date=date(2026, 10, 3)
        )
    )
    assert output.status == "UNKNOWN"
    assert output.available_windows == []


def test_knowledge_search_filters_by_destination() -> None:
    output = client.search_travel_knowledge(
        SearchTravelKnowledgeRequest(query="", destination_ids=["dest_chengdu"], top_k=10)
    )
    assert output.evidence
    for item in output.evidence:
        assert item.evidence_id
        assert item.entity_id
        assert item.content
        assert item.acquisition_status == "MOCK_ONLY"


def test_unrelated_knowledge_query_returns_empty() -> None:
    output = client.search_travel_knowledge(
        SearchTravelKnowledgeRequest(
            query="量子芯片 编译器",
            destination_ids=["dest_chengdu"],
            top_k=10,
        )
    )
    assert output.evidence == []


def test_route_is_deterministic_and_marked_estimated() -> None:
    request = GetRouteRequest(origin="poi_1001", destination="poi_1003")
    first = client.get_route(request)
    second = client.get_route(request)
    assert first == second
    assert first.routes
    route = first.routes[0]
    assert route.is_estimated is True
    assert route.source == "MOCK"
    assert route.duration_minutes > 0
    assert route.distance_km and route.distance_km > 0


def test_weather_is_deterministic_and_marked_forecast() -> None:
    request = GetWeatherRequest(
        date_range=DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 4)),
        destination_id="dest_chengdu",
    )
    assert client.get_weather(request) == client.get_weather(request)
    output = client.get_weather(request)
    assert len(output.weather_facts) == 3
    for fact in output.weather_facts:
        assert fact.is_forecast is True
        assert fact.source == "MOCK"
        assert fact.data_assurance_status == "MOCK"
        assert 0 <= (fact.precipitation_probability or 0) <= 1


def test_weather_missing_day_reports_data_missing() -> None:
    import pytest

    request = GetWeatherRequest(
        date_range=DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 5)),
        destination_id="dest_chengdu",
    )
    with pytest.raises(DataMissingError) as error:
        client.get_weather(request)
    assert error.value.code == "DATA_MISSING"
    assert error.value.missing_dates == (date(2026, 10, 5),)


def test_intercity_date_mismatch_returns_empty() -> None:
    output = client.get_intercity_options(
        GetIntercityOptionsRequest(
            origin_city="上海",
            destination_id="dest_chengdu",
            arrival_or_departure_date=date(2026, 10, 3),
        )
    )
    assert output.options == []


def test_daily_entry_window_uses_requested_date() -> None:
    requested = date(2026, 10, 3)
    output = client.get_resource_availability(
        GetResourceAvailabilityRequest(resource_id="poi_1001", date=requested)
    )
    assert output.available_windows
    window = output.available_windows[0]
    assert window.start_at.date() == requested
    assert window.end_at.date() == requested
    assert window.end_at.strftime("%H:%M") == "16:30"


def test_preparation_rules_use_weather_activity_and_user_conditions() -> None:
    profile = _profile().model_copy(
        update={"mobility_constraints": ["LIMITED_WALKING"]}
    )
    weather = client.get_weather(
        GetWeatherRequest(
            date_range=DateRange(
                start_date=date(2026, 10, 2), end_date=date(2026, 10, 3)
            ),
            destination_id="dest_chengdu",
        )
    )
    output = client.get_preparation_rules(
        GetPreparationRulesRequest(
            trip_profile=profile,
            activity_tags=["OUTDOOR"],
            weather_facts=weather.weather_facts,
        )
    )
    assert {item.rule_id for item in output.rules} == {
        "prep_identity",
        "prep_rain",
        "prep_outdoor",
        "prep_limited_walking",
    }

