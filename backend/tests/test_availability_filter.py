"""C3 前置过滤测试。

覆盖正常场景、失败场景（明确不可用）和数据不足场景（UNKNOWN），
对应 `docs/SCOPE_MATRIX.md`「不可用地点被前置过滤」的验收方式。
"""

from __future__ import annotations

from datetime import date

from app.schemas import RunMode, VisitPlaceCandidate
from app.schemas.v04.mcp import GetResourceAvailabilityResponse
from app.services.availability_filter import (
    filter_candidates,
    filter_candidates_for_trip,
    is_usable,
)

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


# --- 整段行程的逐日过滤（接入 LangGraph 的形态） -----------------------------

TRIP = [DATE, date(2026, 10, 4), date(2026, 10, 5)]


def _dated_lookup(mapping: dict[str, dict[date, str]]):
    def _inner(resource_id: str, travel_date: date) -> GetResourceAvailabilityResponse:
        status = mapping.get(resource_id, {}).get(travel_date, "AVAILABLE")
        reason = f"{resource_id} {travel_date.isoformat()} 状态：{status}"
        return GetResourceAvailabilityResponse(status=status, reason=reason)

    return _inner


def test_trip_filter_excludes_resource_unavailable_on_every_day() -> None:
    """整段行程都闭馆的资源必须被排除（P0 不变量 2）。"""

    result = filter_candidates_for_trip(
        [_candidate("poi_closed", "UNAVAILABLE")],
        travel_dates=TRIP,
        availability_lookup=_dated_lookup({"poi_closed": {d: "UNAVAILABLE" for d in TRIP}}),
    )
    assert result.plannable == []
    assert result.excluded[0].resource_id == "poi_closed"
    assert result.excluded[0].reason


def test_trip_filter_keeps_partially_closed_resource_as_conditional() -> None:
    """只在部分日期闭馆的资源可以保留，但不得充当无条件主方案。"""

    result = filter_candidates_for_trip(
        [_candidate("poi_partial", "AVAILABLE")],
        travel_dates=TRIP,
        availability_lookup=_dated_lookup({"poi_partial": {TRIP[1]: "UNAVAILABLE"}}),
    )
    assert result.usable == []
    assert [item.resource_id for item in result.conditional] == ["poi_partial"]
    assert result.has_unconditional_primary is False


def test_trip_filter_records_unavailable_dates_for_the_planner() -> None:
    """禁排日期要留给 C4 做增量检查，不能只丢一个布尔结果。"""

    result = filter_candidates_for_trip(
        [_candidate("poi_partial", "AVAILABLE")],
        travel_dates=TRIP,
        availability_lookup=_dated_lookup({"poi_partial": {TRIP[0]: "UNAVAILABLE"}}),
    )
    assert result.unavailable_dates == {"poi_partial": [TRIP[0]]}
    assert result.checked_dates == TRIP


def test_trip_filter_uses_the_most_conservative_day_status() -> None:
    """同一天未知、另一天可用时按未知处理，不允许把不确定当确定。"""

    result = filter_candidates_for_trip(
        [_candidate("poi_mix", "AVAILABLE")],
        travel_dates=TRIP,
        availability_lookup=_dated_lookup({"poi_mix": {TRIP[2]: "UNKNOWN"}}),
    )
    assert [item.resource_id for item in result.unknown] == ["poi_mix"]
    assert result.usable == []


def test_trip_filter_verified_mode_excludes_unknown() -> None:
    result = filter_candidates_for_trip(
        [_candidate("poi_mix", "AVAILABLE")],
        travel_dates=TRIP,
        availability_lookup=_dated_lookup({"poi_mix": {TRIP[2]: "UNKNOWN"}}),
        run_mode=RunMode.VERIFIED,
    )
    assert result.excluded[0].resource_id == "poi_mix"
    assert result.has_any_candidate is False


def test_trip_filter_without_dates_falls_back_to_candidate_status() -> None:
    result = filter_candidates_for_trip(
        [_candidate("poi_1", "AVAILABLE")],
        travel_dates=[],
        availability_lookup=_dated_lookup({}),
    )
    assert [item.resource_id for item in result.usable] == ["poi_1"]
