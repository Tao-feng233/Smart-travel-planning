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
from app.services.v04_mock_provider import (
    CLOSED_DATES,
    DataMissingError,
    V04MockMCPProvider,
)

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
    """没有可检索资源的目的地不能仅靠元数据进入推荐。"""

    short = {item.destination_id for item in _search(days=2).recommendations}
    long = {item.destination_id for item in _search(days=5).recommendations}
    assert "dest_leshan" not in short
    assert "dest_leshan" not in long
    assert "dest_chengdu" in long


def test_v2_readiness_threshold_supports_six_day_trip() -> None:
    output = _search(days=6)
    evaluation = next(
        item
        for item in output.readiness_evaluations
        if item.destination_id == "dest_chengdu"
    )

    assert evaluation.ruleset_version == "rules-2026-09-27-v2"
    assert evaluation.planning_ready is True
    assert "VISIT_PLACE_COVERAGE" not in evaluation.failed_requirements


def test_visit_place_coverage_matches_public_search_for_every_destination() -> None:
    expected_available_counts = {
        "dest_chengdu": 10,
        "dest_leshan": 0,
        "dest_dujiangyan": 0,
    }
    evaluations = {
        item.destination_id: item for item in _search(days=5).readiness_evaluations
    }
    assert set(evaluations) == set(expected_available_counts)

    for destination_id, evaluation in evaluations.items():
        resources = client.search_resources(
            SearchResourcesRequest(
                resource_type="VISIT_PLACE",
                destination_id=destination_id,
                date_range=DateRange(
                    start_date=date(2026, 10, 2), end_date=date(2026, 10, 6)
                ),
            )
        ).resources
        available = [
            item
            for item in resources
            if item.availability_status in ("AVAILABLE", "CONDITIONAL")
        ]
        expected_count = expected_available_counts[destination_id]
        assert len(available) == expected_count
        assert (
            "VISIT_PLACE_COVERAGE" in evaluation.failed_requirements
        ) is (expected_count < 9)


def test_readiness_does_not_count_unavailable_places(monkeypatch) -> None:
    closed_for_trip = {date(2026, 10, day) for day in range(2, 7)}
    monkeypatch.setitem(CLOSED_DATES, "poi_1001", closed_for_trip)
    monkeypatch.setitem(CLOSED_DATES, "poi_1003", closed_for_trip)

    evaluation = next(
        item
        for item in _search(days=5).readiness_evaluations
        if item.destination_id == "dest_chengdu"
    )
    assert "VISIT_PLACE_COVERAGE" in evaluation.failed_requirements


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


def test_recommendation_days_follow_destination_range() -> None:
    item = next(
        item
        for item in _search(days=5).recommendations
        if item.destination_id == "dest_chengdu"
    )
    assert item.suggested_days == 5


def test_recommendation_days_respect_destination_minimum() -> None:
    item = next(
        item
        for item in _search(days=1).recommendations
        if item.destination_id == "dest_chengdu"
    )
    assert item.suggested_days == 2


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


def test_lodging_search_returns_two_areas_and_four_mock_candidates() -> None:
    date_range = DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 6))
    lodgings = client.search_resources(
        SearchResourcesRequest(
            resource_type="LODGING",
            destination_id="dest_chengdu",
            date_range=date_range,
        )
    ).resources
    areas = client.search_resources(
        SearchResourcesRequest(
            resource_type="LODGING_AREA",
            destination_id="dest_chengdu",
            date_range=date_range,
        )
    ).resources

    assert len(lodgings) == 4
    assert len(areas) == 2
    assert {item.area_id for item in lodgings} == {item.resource_id for item in areas}
    for item in lodgings:
        assert item.resource_id.startswith("lodging_")
        assert item.price_range.min_amount is not None
        assert item.price_range.max_amount is not None
        assert item.commute_summary
        assert item.lodging_area
        assert item.availability_is_realtime is False


def test_candidate_evidence_points_to_the_same_resource() -> None:
    date_range = DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 6))
    resources = []
    for resource_type in ("VISIT_PLACE", "RESTAURANT", "LODGING", "LODGING_AREA"):
        resources.extend(
            client.search_resources(
                SearchResourcesRequest(
                    resource_type=resource_type,
                    destination_id="dest_chengdu",
                    date_range=date_range,
                )
            ).resources
        )
    evidence = client.search_travel_knowledge(
        SearchTravelKnowledgeRequest(
            query="", destination_ids=["dest_chengdu"], top_k=50
        )
    ).evidence
    evidence_by_id = {item.evidence_id: item for item in evidence}

    for resource in resources:
        assert resource.evidence_ids
        for evidence_id in resource.evidence_ids:
            assert evidence_by_id[evidence_id].entity_id == resource.resource_id


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


def test_route_matrix_covers_demo_places_restaurant_and_lodging() -> None:
    pairs = [
        ("poi_1001", "poi_1002"),
        ("poi_1002", "poi_1001"),
        ("poi_1001", "rest_2001"),
        ("rest_2001", "poi_1003"),
        ("lodging_3004", "poi_1001"),
        ("成都东站", "lodging_3004"),
        ("lodging_3004", "成都东站"),
    ]
    for origin, destination in pairs:
        output = client.get_route(GetRouteRequest(origin=origin, destination=destination))
        assert output.routes, f"missing mock route: {origin} -> {destination}"
        assert output.routes[0].source == "MOCK"
        assert output.routes[0].is_estimated is True


def test_weather_is_deterministic_and_marked_forecast() -> None:
    request = GetWeatherRequest(
        date_range=DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 6)),
        destination_id="dest_chengdu",
    )
    assert client.get_weather(request) == client.get_weather(request)
    output = client.get_weather(request)
    assert len(output.weather_facts) == 5
    for fact in output.weather_facts:
        assert fact.is_forecast is True
        assert fact.source == "MOCK"
        assert fact.data_assurance_status == "MOCK"
        assert 0 <= (fact.precipitation_probability or 0) <= 1


def test_weather_missing_day_reports_data_missing() -> None:
    import pytest

    request = GetWeatherRequest(
        date_range=DateRange(start_date=date(2026, 10, 2), end_date=date(2026, 10, 7)),
        destination_id="dest_chengdu",
    )
    with pytest.raises(DataMissingError) as error:
        client.get_weather(request)
    assert error.value.code == "DATA_MISSING"
    assert error.value.missing_dates == (date(2026, 10, 7),)


def test_intercity_date_mismatch_returns_empty() -> None:
    output = client.get_intercity_options(
        GetIntercityOptionsRequest(
            origin_city="上海",
            destination_id="dest_chengdu",
            arrival_or_departure_date=date(2026, 10, 3),
        )
    )
    assert output.options == []


def test_return_intercity_option_matches_demo_end_date() -> None:
    output = client.get_intercity_options(
        GetIntercityOptionsRequest(
            origin_city="dest_chengdu",
            destination_id="上海",
            arrival_or_departure_date=date(2026, 10, 6),
        )
    )
    assert len(output.options) == 1
    assert output.options[0].origin_station == "成都东站"
    assert output.options[0].destination_station == "上海虹桥站"


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

