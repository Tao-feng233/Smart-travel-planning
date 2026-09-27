"""C5 验证器测试：每类冲突都要查得出，并且给得出修复选项。

计划对象用 `test_itinerary_planner` 的假 Provider 先生成（A 的数据到位后
可以直接换成 `V04MockMCPProvider`），再按用例需要做最小改写。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.schemas import (
    Conflict,
    ItineraryPlan,
    Money,
    PlanValidationStatus,
    RunMode,
    TripProfile,
)
from app.services.availability_filter import ExcludedCandidate, TripFilterResult
from app.services.plan_validator import attach_validation, validate_plan
from test_itinerary_planner import _build, _candidates, _profile


def _plan() -> ItineraryPlan:
    outcome = _build()
    assert outcome.plan is not None
    return outcome.plan


def _with_budget(amount: float, *, flexibility: str = "NEGOTIABLE") -> TripProfile:
    return _profile().model_copy(
        update={
            "budget": Money(amount=amount, currency="CNY"),
            "budget_flexibility": flexibility,
        }
    )


def _first_node(plan: ItineraryPlan, node_type: str):
    return next(node for node in plan.nodes if node.node_type == node_type)


def _retarget(plan: ItineraryPlan, node_id: str, resource_id: str) -> ItineraryPlan:
    nodes = [
        node.model_copy(update={"resource_id": resource_id})
        if node.node_id == node_id
        else node
        for node in plan.nodes
    ]
    return plan.model_copy(update={"nodes": nodes})


# --- 正常场景 ---------------------------------------------------------------


def test_clean_plan_is_valid() -> None:
    result = validate_plan(_plan(), profile=_profile())
    assert result.status == PlanValidationStatus.VALID
    assert result.errors == []


def test_unknown_ticket_price_is_warning_not_error_in_demo() -> None:
    prior = [
        Conflict(
            conflict_id="conflict_ticket_price_unknown",
            type="DATA_UNKNOWN",
            severity="WARNING",
            scope="COST",
            message="景点门票价格暂无数据。",
        )
    ]
    result = validate_plan(_plan(), profile=_profile(), prior_conflicts=prior)
    assert result.status == PlanValidationStatus.VALID
    # 同一条数据缺口只出现一次（不能既从 prior 进来又重发一遍）
    assert [item.conflict_id for item in result.conflicts] == [
        "conflict_ticket_price_unknown"
    ]


def test_same_unknown_fact_blocks_verified_mode() -> None:
    """§14 不变量 3：UNKNOWN 关键事实阻止 VERIFIED 模式发布。"""

    prior = [
        Conflict(
            conflict_id="conflict_ticket_price_unknown",
            type="DATA_UNKNOWN",
            severity="WARNING",
            scope="COST",
            message="景点门票价格暂无数据。",
        )
    ]
    result = validate_plan(
        _plan(), profile=_profile(), prior_conflicts=prior, run_mode=RunMode.VERIFIED
    )
    assert result.status == PlanValidationStatus.INVALID
    assert result.errors


# --- 资源不可用（P0 验收的"闭馆替换"场景） --------------------------------


def test_excluded_resource_is_error_with_replacement_options() -> None:
    plan = _plan()
    attraction = _first_node(plan, "ATTRACTION")
    broken = _retarget(plan, attraction.node_id, "poi_1002")
    filter_result = TripFilterResult(
        excluded=[
            ExcludedCandidate(
                resource_id="poi_1002", status="UNAVAILABLE", reason="行程期内闭馆"
            )
        ]
    )
    result = validate_plan(
        broken,
        profile=_profile(),
        candidates=_candidates(),
        filter_result=filter_result,
    )
    assert result.status == PlanValidationStatus.INVALID
    conflict = result.errors[0]
    assert conflict.type == "OPENING_HOURS"
    actions = [option.action for option in conflict.repair_options]
    assert "REPLACE_RESOURCE" in actions, "闭馆必须给得出替换方案（P0 验收）"


def test_resource_unavailable_on_a_specific_day_is_error() -> None:
    plan = _plan()
    attraction = _first_node(plan, "ATTRACTION")
    day = attraction.start_at.date()
    filter_result = TripFilterResult(
        unavailable_dates={attraction.resource_id: [day]}
    )
    result = validate_plan(plan, profile=_profile(), filter_result=filter_result)
    assert result.status == PlanValidationStatus.INVALID
    assert any("不可用" in item.message for item in result.errors)


def test_candidate_marked_unavailable_is_error() -> None:
    plan = _plan()
    attraction = _first_node(plan, "ATTRACTION")
    patched = [
        item.model_copy(update={"availability_status": "UNAVAILABLE"})
        if item.resource_id == attraction.resource_id
        else item
        for item in _candidates()
    ]
    result = validate_plan(plan, profile=_profile(), candidates=patched)
    assert result.status == PlanValidationStatus.INVALID


# --- 时间窗口 ---------------------------------------------------------------


def test_overlapping_nodes_are_error() -> None:
    plan = _plan()
    first = _first_node(plan, "ATTRACTION")
    second = next(
        node
        for node in plan.nodes
        if node.node_type == "ATTRACTION"
        and node.node_id != first.node_id
        and node.start_at.date() == first.start_at.date()
    )
    nodes = [
        node.model_copy(update={"start_at": first.start_at, "end_at": first.end_at})
        if node.node_id == second.node_id
        else node
        for node in plan.nodes
    ]
    result = validate_plan(plan.model_copy(update={"nodes": nodes}), profile=_profile())
    assert result.status == PlanValidationStatus.INVALID
    assert any(item.type == "TIME_WINDOW" for item in result.errors)
    assert any(
        option.action == "REORDER_NODES"
        for item in result.errors
        for option in item.repair_options
    )


def test_node_outside_opening_hours_is_error() -> None:
    plan = _plan()
    attraction = _first_node(plan, "ATTRACTION")
    late = attraction.start_at.replace(hour=23)
    nodes = [
        node.model_copy(
            update={"start_at": late, "end_at": late + timedelta(minutes=60)}
        )
        if node.node_id == attraction.node_id
        else node
        for node in plan.nodes
    ]
    result = validate_plan(
        plan.model_copy(update={"nodes": nodes}),
        profile=_profile(),
        candidates=_candidates(),
    )
    assert result.status == PlanValidationStatus.INVALID
    assert any("不在开放时间" in item.message for item in result.errors)


def test_earliest_day_start_is_respected() -> None:
    """用户说「不想早起」（软约束已写进 earliest_day_start）时要能查出来。"""

    profile = _profile().model_copy(update={"earliest_day_start": "12:00"})
    result = validate_plan(_plan(), profile=profile)
    assert result.status == PlanValidationStatus.INVALID
    assert any("早于用户要求" in item.message for item in result.errors)


# --- 预算 -------------------------------------------------------------------


def test_budget_exceeded_is_error_with_repairs() -> None:
    plan = _build(profile=_with_budget(1000)).plan
    assert plan is not None
    result = validate_plan(plan, profile=_with_budget(1000))
    assert result.status == PlanValidationStatus.INVALID
    conflict = next(item for item in result.errors if item.type == "BUDGET_EXCEEDED")
    actions = {option.action for option in conflict.repair_options}
    assert "RELAX_NEGOTIABLE_CONSTRAINT" in actions  # 预算可协商


def test_fixed_budget_cannot_be_relaxed_automatically() -> None:
    """固定预算不得被自动突破：只能请用户决定（§14）。"""

    profile = _with_budget(1000, flexibility="FIXED")
    plan = _build(profile=profile).plan
    assert plan is not None
    result = validate_plan(plan, profile=profile)
    conflict = next(item for item in result.errors if item.type == "BUDGET_EXCEEDED")
    actions = {option.action for option in conflict.repair_options}
    assert "RELAX_NEGOTIABLE_CONSTRAINT" not in actions
    assert "REQUEST_USER_CHOICE" in actions


def test_budget_near_limit_is_warning_only() -> None:
    baseline = _build(profile=_with_budget(100_000)).plan
    assert baseline is not None
    limit = round(baseline.budget_summary.estimated_max_total * 1.05)
    profile = _with_budget(limit)
    plan = _build(profile=profile).plan
    assert plan is not None
    result = validate_plan(plan, profile=profile)
    assert result.status == PlanValidationStatus.VALID
    assert [item.severity for item in result.conflicts] == ["WARNING"]
    assert result.conflicts[0].type == "BUDGET_EXCEEDED"


# --- 强度与移动 -------------------------------------------------------------


def test_long_travel_with_mobility_constraint_is_error() -> None:
    plan = _plan()
    legs = [
        leg.model_copy(update={"duration_minutes": 90}) for leg in plan.travel_legs
    ]
    profile = _profile().model_copy(update={"mobility_constraints": ["行动不便"]})
    result = validate_plan(
        plan.model_copy(update={"travel_legs": legs}), profile=profile
    )
    assert result.status == PlanValidationStatus.INVALID
    conflict = next(item for item in result.errors if item.type == "DISTANCE_EXCESSIVE")
    assert [option.action for option in conflict.repair_options] == ["CHANGE_TRAVEL_MODE"]


def test_heavy_day_is_warning() -> None:
    plan = _plan()
    nodes = [
        node.model_copy(update={"end_at": node.start_at + timedelta(minutes=420)})
        if node.node_type == "ATTRACTION"
        else node
        for node in plan.nodes
    ]
    result = validate_plan(plan.model_copy(update={"nodes": nodes}), profile=_profile())
    assert any(item.type == "DAILY_INTENSITY" for item in result.conflicts)


# --- 写回计划 ---------------------------------------------------------------


def test_attach_validation_writes_status_and_conflicts() -> None:
    plan = _plan()
    result = validate_plan(plan, profile=_profile())
    updated = attach_validation(plan, result)
    assert updated.plan_validation_status == PlanValidationStatus.VALID
    assert updated.conflict_ids == [item.conflict_id for item in result.conflicts]


def test_cannot_mark_over_budget_plan_as_valid() -> None:
    """契约不变量：VALID 计划不得在最低估算下超预算（模型会直接拒绝）。"""

    profile = _with_budget(1000)
    plan = _build(profile=profile).plan
    assert plan is not None
    fake_valid = type(
        "FakeResult", (), {"status": PlanValidationStatus.VALID, "conflicts": []}
    )()
    with pytest.raises(ValidationError, match="exceed budget"):
        attach_validation(plan, fake_valid)
