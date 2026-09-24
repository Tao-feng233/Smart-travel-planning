"""C3 前置过滤测试。

覆盖正常场景、失败场景（明确不可用）和数据不足场景（UNKNOWN），
对应 `docs/SCOPE_MATRIX.md`「不可用地点被前置过滤」的验收方式。
"""

from __future__ import annotations

from datetime import date

from app.schemas import RunMode, VisitPlaceCandidate
from app.schemas.v04.mcp import GetResourceAvailabilityResponse
from app.services.availability_filter import filter_candidates, is_usable

DATE = date(2026, 10, 3)


def _candidate(resource_id: str, status: str) -> VisitPlaceCandidate:
    return VisitPlaceCandidate(
        resource_id=resource_id,
        destination_id="dest_chengdu",
        area_id="area_001",
        name=f"示例地点 {resource_id}",
        address="示例地址",
        latitude=30.0,
        longitude=104.0,
        categories=["CULTURE"],
        suggested_duration_minutes=120,
        availability_status=status,
        opening_windows=[],
        physical_intensity="LOW",
        indoor=True,
        weather_sensitivity="LOW",
        planning_fact_ids=[],
        evidence_ids=[],
    )


def _lookup(mapping: dict[str, str]):
    def _inner(resource_id: str, _date: date) -> GetResourceAvailabilityResponse:
        status = mapping.get(resource_id, "UNKNOWN")
        return GetResourceAvailabilityResponse(
            status=status, reason=f"{resource_id} 当日状态：{status}"
        )

    return _inner


def test_available_candidates_enter_planning() -> None:
    result = filter_candidates([_candidate("poi_1", "AVAILABLE")])
    assert [c.resource_id for c in result.usable] == ["poi_1"]
    assert result.excluded == []
    assert result.has_unconditional_primary is True


def test_unavailable_candidate_is_never_plannable() -> None:
    """P0 不变量：UNAVAILABLE 绝不进入规划。"""

    bad = _candidate("poi_closed", "UNAVAILABLE")
    result = filter_candidates([bad, _candidate("poi_ok", "AVAILABLE")])
    assert [c.resource_id for c in result.plannable] == ["poi_ok"]
    assert [e.resource_id for e in result.excluded] == ["poi_closed"]
    assert result.excluded[0].reason
    assert is_usable(bad, result) is False


def test_conditional_candidate_keeps_conditions() -> None:
    result = filter_candidates([_candidate("poi_resv", "CONDITIONAL")])
    assert result.usable == []
    assert [c.resource_id for c in result.conditional] == ["poi_resv"]
    # 有条件可用可以进入规划，但不能充当"无条件主方案"
    assert result.has_unconditional_primary is False


def test_unknown_candidate_is_not_an_unconditional_primary() -> None:
    result = filter_candidates([_candidate("poi_unknown", "UNKNOWN")])
    assert result.usable == []
    assert [c.resource_id for c in result.unknown] == ["poi_unknown"]


def test_verified_mode_rejects_unknown_facts() -> None:
    result = filter_candidates(
        [_candidate("poi_unknown", "UNKNOWN")], run_mode=RunMode.VERIFIED
    )
    assert result.plannable == []
    assert result.excluded[0].reason


def test_daily_availability_overrides_candidate_status() -> None:
    """候选整体可用，但当天临时闭馆时必须被过滤掉。"""

    result = filter_candidates(
        [_candidate("poi_1", "AVAILABLE")],
        travel_date=DATE,
        availability_lookup=_lookup({"poi_1": "UNAVAILABLE"}),
    )
    assert result.plannable == []
    assert result.excluded[0].status == "UNAVAILABLE"


def test_daily_availability_can_rescue_unknown_candidate() -> None:
    result = filter_candidates(
        [_candidate("poi_1", "UNKNOWN")],
        travel_date=DATE,
        availability_lookup=_lookup({"poi_1": "AVAILABLE"}),
    )
    assert [c.resource_id for c in result.usable] == ["poi_1"]


def test_empty_input_is_safe() -> None:
    result = filter_candidates([])
    assert result.plannable == []
    assert result.has_unconditional_primary is False


def test_missing_status_is_treated_as_unknown_not_available() -> None:
    """没有可用性字段时按未知处理，绝不默认放行。"""

    candidate = _candidate("poi_1", "AVAILABLE").model_copy()
    object.__setattr__(candidate, "availability_status", None)
    result = filter_candidates([candidate])
    assert result.usable == []
