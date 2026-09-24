"""契约示例 JSON 校验测试。

目的：把 `CONTRACTS.md` 中的示例 JSON 全部转成可执行的校验用例。
只要 A/B 两条线少给一个字段、写错一个枚举值，或有人偷偷新增字段，
这里就会失败，而不是等到联调时才发现。

运行：在 backend 目录执行 `python -m pytest`
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.schemas import (
    Conflict,
    DestinationRecommendation,
    Evidence,
    GetPlaceAvailabilityInput,
    GetPlaceAvailabilityOutput,
    GetPlaceFactsInput,
    GetPlaceFactsOutput,
    GetRouteInput,
    GetRouteOutput,
    GetWeatherInput,
    GetWeatherOutput,
    ItineraryPlan,
    KnowledgeCoverage,
    PlanState,
    ResourceCandidate,
    SearchPlanningReadyDestinationsInput,
    SearchPlanningReadyDestinationsOutput,
    SearchTravelKnowledgeInput,
    SearchTravelKnowledgeOutput,
    TravelGuide,
    TripProfile,
    UserAction,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    """读取 fixture，供三条开发线复用。"""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_trip_profile_example() -> None:
    profile = TripProfile.model_validate(load("trip_profile"))
    assert profile.duration_days == 5
    assert profile.destination_mode.value == "UNKNOWN"


def test_knowledge_coverage_example() -> None:
    coverage = KnowledgeCoverage.model_validate(load("knowledge_coverage"))
    assert coverage.planning_ready is True
    assert coverage.missing_capabilities == ["REALTIME_HOTEL_AVAILABILITY"]


def test_destination_recommendation_example() -> None:
    rec = DestinationRecommendation.model_validate(load("destination_recommendation"))
    assert rec.destination_id == "dest_chengdu"
    assert rec.evidence_ids


def test_evidence_example() -> None:
    items = [Evidence.model_validate(x) for x in load("evidence")]
    assert {e.evidence_id for e in items} == {"ev_101", "ev_301"}
    # 模拟数据必须显式标记，不得伪装成已核验事实
    assert all(e.acquisition_status.value == "MOCK_ONLY" for e in items)


def test_resource_candidate_examples() -> None:
    candidates = [ResourceCandidate.model_validate(x) for x in load("resource_candidates")]
    assert len(candidates) == 3
    statuses = {c.availability.status.value for c in candidates}
    assert statuses == {"AVAILABLE", "UNAVAILABLE", "CONDITIONAL"}
    unavailable = next(c for c in candidates if c.availability.status.value == "UNAVAILABLE")
    assert unavailable.availability.reason, "UNAVAILABLE 必须给出原因"


def test_itinerary_plan_example() -> None:
    plan = ItineraryPlan.model_validate(load("itinerary_plan"))
    assert plan.status.value == "VALIDATED"
    assert len(plan.segments) == 1, "P0 只允许一个目的地分段"
    day = plan.days[0]
    assert len(day.nodes) >= 2, "单日必须包含多个游玩/用餐节点"
    assert day.travel_legs, "节点之间必须有移动段"
    assert day.travel_legs[0].from_node_id != day.travel_legs[0].to_node_id


def test_travel_guide_example_has_seven_sections() -> None:
    guide = TravelGuide.model_validate(load("travel_guide"))
    for section in (
        "trip_summary",
        "arrival_and_departure",
        "preparation",
        "lodging",
        "daily_itinerary",
        "budget_and_alternatives",
        "sources_and_freshness",
    ):
        assert section in guide.model_dump(), f"缺少攻略第七部分：{section}"
    assert guide.sources_and_freshness.unknown_items, "无法获得的字段必须显式列出"


def test_conflict_example() -> None:
    conflict = Conflict.model_validate(load("conflict"))
    assert conflict.severity.value == "ERROR"
    assert conflict.repair_options[0].action == "REORDER_NODES"


def test_plan_state_example() -> None:
    state = PlanState.model_validate(load("plan_state"))
    assert state.profile is None
    assert state.stage == "VALIDATING"


def test_plan_state_accepts_nested_plan_and_guide() -> None:
    """验证前向引用：PlanState.current_plan / current_guide 能装下完整对象。"""
    raw = load("plan_state")
    raw["profile"] = load("trip_profile")
    raw["current_plan"] = load("itinerary_plan")
    raw["current_guide"] = load("travel_guide")
    raw["destination_candidates"] = [load("destination_recommendation")]
    raw["resource_candidates"] = load("resource_candidates")
    raw["conflicts"] = [load("conflict")]
    state = PlanState.model_validate(raw)
    assert state.current_plan is not None and state.current_guide is not None
    assert state.current_plan.days[0].nodes[0].node_id == "node_01"


def test_user_action_example() -> None:
    action = UserAction.model_validate(load("user_action"))
    assert action.action_type.value == "MODIFY_GUIDE"
    assert action.payload is not None
    assert action.payload.change_type.value == "LOWER_INTENSITY"
    assert action.payload.scope_hint.value == "DAY"


MCP_TOOL_CASES = {
    "search_planning_ready_destinations": (
        SearchPlanningReadyDestinationsInput,
        SearchPlanningReadyDestinationsOutput,
    ),
    "search_travel_knowledge": (
        SearchTravelKnowledgeInput,
        SearchTravelKnowledgeOutput,
    ),
    "get_place_facts": (GetPlaceFactsInput, GetPlaceFactsOutput),
    "get_place_availability": (GetPlaceAvailabilityInput, GetPlaceAvailabilityOutput),
    "get_route": (GetRouteInput, GetRouteOutput),
    "get_weather": (GetWeatherInput, GetWeatherOutput),
}


@pytest.mark.parametrize("tool_name", sorted(MCP_TOOL_CASES))
def test_mcp_tool_io(tool_name: str) -> None:
    input_model, output_model = MCP_TOOL_CASES[tool_name]
    raw = load("mcp_tool_io")[tool_name]
    input_model.model_validate(raw["input"])
    output_model.model_validate(raw["output"])


def test_examples_round_trip() -> None:
    """序列化结果必须能重新通过校验，保证写入数据库/接口后不回退。"""
    for name, model in (
        ("trip_profile", TripProfile),
        ("knowledge_coverage", KnowledgeCoverage),
        ("itinerary_plan", ItineraryPlan),
        ("travel_guide", TravelGuide),
        ("plan_state", PlanState),
        ("conflict", Conflict),
        ("user_action", UserAction),
    ):
        instance = model.model_validate(load(name))
        dumped = instance.model_dump(mode="json")
        model.model_validate(dumped)


def test_clock_format_is_preserved() -> None:
    """HH:MM 不应被序列化成 HH:MM:SS，保证接口输出与契约示例逐字一致。"""
    plan = ItineraryPlan.model_validate(load("itinerary_plan"))
    dumped = plan.model_dump(mode="json")
    assert dumped["days"][0]["nodes"][0]["start_time"] == "09:30"
    assert dumped["days"][0]["travel_legs"][0]["arrive_time"] == "11:55"
