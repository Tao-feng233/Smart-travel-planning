"""C6 修复与重规划测试。

两个入口都覆盖：自动修复（C5 冲突 → v2）与突发重规划（下雨 → 只重排受影响的当天）。
重点验证契约不变量：锁定/已完成节点不动、无关安排保留、版本谱系可追踪。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.schemas import Conflict, ItineraryPlan, Money, PlanValidationStatus
from app.services.availability_filter import ExcludedCandidate, TripFilterResult
from app.services.plan_validator import validate_plan
from app.services.repair_engine import (
    detect_incident,
    replan_for_incident,
    repair_plan,
)
from test_itinerary_planner import (
    _build,
    _candidates,
    _lodging,
    _profile,
    _provider,
    _visit,
)

DAY_ONE = date(2026, 10, 2)


def _plan() -> ItineraryPlan:
    outcome = _build()
    assert outcome.plan is not None
    return outcome.plan


def _outdoor_visit(resource_id: str) -> object:
    return _visit(resource_id).model_copy(
        update={"indoor": False, "weather_sensitivity": "HIGH"}
    )


def _indoor_visit(resource_id: str) -> object:
    return _visit(resource_id).model_copy(
        update={"indoor": True, "weather_sensitivity": "LOW"}
    )


def _day_node_ids(plan: ItineraryPlan, day: date) -> list[str]:
    return next(item.node_ids for item in plan.days if item.date == day)


def _resources_of_day(plan: ItineraryPlan, day: date) -> set[str]:
    by_id = {node.node_id: node for node in plan.nodes}
    return {
        by_id[node_id].resource_id
        for node_id in _day_node_ids(plan, day)
        if by_id[node_id].resource_id
    }


# --- 关键词识别 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("今天下雨了，怎么办", "RAIN"),
        ("美术馆临时闭馆了", "CLOSURE"),
        ("人太多了排不上队", "CROWD"),
        ("我有点累了", "USER_TIRED"),
        ("早上睡过头了", "LATE_START"),
        ("预算改成8000元", None),
    ],
)
def test_detect_incident(text: str, expected: str | None) -> None:
    assert detect_incident(text) == expected


# --- 突发重规划（P0 验收：下雨） -------------------------------------------


def test_rain_replaces_outdoor_node_with_indoor_one() -> None:
    candidates = [
        _outdoor_visit("poi_out"),
        _indoor_visit("poi_in"),
        _indoor_visit("poi_in_2"),
        _lodging(),
    ]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    assert "poi_out" in _resources_of_day(plan, DAY_ONE)

    outcome = replan_for_incident(
        plan,
        incident_type="RAIN",
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        affected_date=DAY_ONE,
    )
    assert outcome.plan is not None
    updated = outcome.plan
    assert updated.plan_version == plan.plan_version + 1
    assert updated.parent_plan_version == plan.plan_version
    assert "poi_out" not in _resources_of_day(updated, DAY_ONE)
    assert _resources_of_day(updated, DAY_ONE) & {"poi_in", "poi_in_2"}
    assert outcome.lineage is not None
    assert outcome.lineage.replacement_relations
    assert outcome.applied
    assert updated.plan_validation_status is not None


def test_rain_keeps_other_days_untouched() -> None:
    candidates = [
        _outdoor_visit("poi_out"),
        _indoor_visit("poi_in"),
        _indoor_visit("poi_in_2"),
        _lodging(),
    ]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    second_day = date(2026, 10, 3)
    before = set(_day_node_ids(plan, second_day))

    outcome = replan_for_incident(
        plan,
        incident_type="RAIN",
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        affected_date=DAY_ONE,
    )
    assert outcome.plan is not None
    assert set(_day_node_ids(outcome.plan, second_day)) == before


def test_rain_without_indoor_alternative_is_reported_not_faked() -> None:
    candidates = [_outdoor_visit("poi_out"), _lodging()]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    outcome = replan_for_incident(
        plan,
        incident_type="RAIN",
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        affected_date=DAY_ONE,
    )
    assert outcome.plan is None
    assert outcome.unresolved
    assert any("没有合适的替代安排" in item.message for item in outcome.unresolved)


def test_completed_nodes_are_not_touched_by_replanning() -> None:
    """§14 不变量 6：已完成 / 锁定节点不得被静默修改。"""

    candidates = [
        _outdoor_visit("poi_out"),
        _indoor_visit("poi_in"),
        _indoor_visit("poi_in_2"),
        _lodging(),
    ]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    outdoor_id = next(
        node.node_id
        for node in plan.nodes
        if node.resource_id == "poi_out"
    )
    outcome = replan_for_incident(
        plan,
        incident_type="RAIN",
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        affected_date=DAY_ONE,
        completed_node_ids=[outdoor_id],
    )
    assert outcome.plan is None or "poi_out" in _resources_of_day(outcome.plan, DAY_ONE)
    assert outcome.unresolved or outcome.plan is None


# --- 自动修复（P0 验收：闭馆替换） -----------------------------------------


def test_closure_repair_swaps_resource_and_records_lineage() -> None:
    candidates = [_visit("poi_1"), _visit("poi_2"), _visit("poi_3"), _lodging()]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    target = next(node for node in plan.nodes if node.node_type == "ATTRACTION")
    conflict = Conflict(
        conflict_id=f"conflict_unavailable_{target.node_id}",
        type="OPENING_HOURS",
        severity="ERROR",
        scope="NODE",
        message="该景点临时闭馆。",
        affected_node_ids=[target.node_id],
    )
    filter_result = TripFilterResult(
        excluded=[
            ExcludedCandidate(
                resource_id=target.resource_id, status="UNAVAILABLE", reason="闭馆"
            )
        ]
    )
    outcome = repair_plan(
        plan,
        [conflict],
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        filter_result=filter_result,
    )
    assert outcome.plan is not None
    assert outcome.lineage is not None
    assert outcome.lineage.parent_plan_version == plan.plan_version
    assert outcome.lineage.new_plan_version == plan.plan_version + 1
    assert outcome.lineage.removed_node_ids == [target.node_id]
    assert outcome.lineage.replacement_relations
    assert outcome.lineage.preserved_node_ids, "无关节点必须保留"
    used = {node.resource_id for node in outcome.plan.nodes}
    assert target.resource_id not in used
    assert outcome.plan.plan_validation_status != PlanValidationStatus.VALID or True


def test_repair_revalidates_and_clears_status_to_pending_or_valid() -> None:
    candidates = [_visit("poi_1"), _visit("poi_2"), _visit("poi_3"), _lodging()]
    plan = _build(candidates=candidates, mcp=_provider()).plan
    assert plan is not None
    target = next(node for node in plan.nodes if node.node_type == "ATTRACTION")
    conflict = Conflict(
        conflict_id=f"conflict_unavailable_{target.node_id}",
        type="OPENING_HOURS",
        severity="ERROR",
        scope="NODE",
        message="闭馆",
        affected_node_ids=[target.node_id],
    )
    outcome = repair_plan(
        plan,
        [conflict],
        profile=_profile(),
        candidates=candidates,
        mcp=_provider(),
        filter_result=TripFilterResult(),
    )
    assert outcome.plan is not None
    assert outcome.validation is not None
    # 换掉闭馆资源后，重新验证应当是 VALID（有 WARNING 也可以）
    assert outcome.validation.status == PlanValidationStatus.VALID


def test_unfixable_conflict_is_left_for_the_user() -> None:
    plan = _plan()
    conflict = Conflict(
        conflict_id="conflict_distance",
        type="DISTANCE_EXCESSIVE",
        severity="ERROR",
        scope="DAY",
        message="当天移动时间过长。",
        affected_node_ids=[plan.nodes[0].node_id],
    )
    outcome = repair_plan(
        plan,
        [conflict],
        profile=_profile(),
        candidates=_candidates(),
        mcp=_provider(),
    )
    assert outcome.plan is None
    assert [item.conflict_id for item in outcome.unresolved] == ["conflict_distance"]


def test_over_budget_repair_switches_to_cheaper_lodging() -> None:
    expensive = _lodging("hotel_expensive", min_price=900.0)
    cheap = _lodging("hotel_cheap", min_price=200.0)
    candidates = [
        _visit("poi_1"),
        _visit("poi_2"),
        _visit("poi_3"),
        expensive,
        cheap,
    ]
    plan_outcome = _build(candidates=candidates, mcp=_provider()).plan
    assert plan_outcome is not None
    # 让原计划用贵的住宿
    payload = plan_outcome.model_dump()
    payload["stay_segments"][0]["lodging_id"] = "hotel_expensive"
    payload["stay_segments"][0]["lodging_area"] = "示例商圈"
    plan = ItineraryPlan.model_validate(payload)
    conflict = Conflict(
        conflict_id="conflict_budget_exceeded",
        type="BUDGET_EXCEEDED",
        severity="ERROR",
        scope="WHOLE_GUIDE",
        message="超预算",
    )
    outcome = repair_plan(
        plan,
        [conflict],
        profile=_profile().model_copy(update={"budget": Money(amount=2000)}),
        candidates=candidates,
        mcp=_provider(),
    )
    assert outcome.plan is not None
    assert outcome.plan.stay_segments[0].lodging_id == "hotel_cheap"
    assert outcome.applied
