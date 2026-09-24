"""B6：攻略组装（`GuideComposer`）测试。

核心是验证两件事：

1. **富化规则与 fixture 一致**：`fixtures/valid/itinerary_plan.json`
   组装出来的每日活动/通勤/费用必须能对上
   `fixtures/valid/travel_guide.json`（费用 50 + 60~100 + 4 = 114~154 那一条）。
2. **红线**：缺城际交通必须明确报缺而不是伪造；DEMO 不得声称 VERIFIED；
   INVALID 计划必须 NOT_READY；`PlanNode` 的字段不得泄漏到 `GuideNode`。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.schemas import (
    ArrivalPlan,
    Conflict,
    DataAssuranceStatus,
    Evidence,
    GuideReadiness,
    IntercityOption,
    ItineraryPlan,
    LodgingAreaCandidate,
    LodgingCandidate,
    Money,
    PlanValidationStatus,
    RestaurantCandidate,
    ReturnPlan,
    RunMode,
    TimeWindow,
    TripProfile,
    VisitPlaceCandidate,
)
from app.guide.composer import (
    GuideCompositionError,
    GuideContext,
    compose_travel_guide,
    derive_data_assurance_status,
    derive_guide_readiness,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "valid"
_NOW = datetime.fromisoformat("2026-09-24T10:00:00+08:00")


def _load(name: str) -> dict:
    raw = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return raw["data"]


def _plan() -> ItineraryPlan:
    return ItineraryPlan.model_validate(_load("itinerary_plan.json"))


def _profile() -> TripProfile:
    return TripProfile.model_validate(_load("trip_profile.json"))


def _context(**overrides) -> GuideContext:
    arrival = _load("travel_guide.json")["arrival_and_departure"]
    base = dict(
        intercity_options=[IntercityOption.model_validate(arrival["recommended_option"])],
        arrival_plan=ArrivalPlan.model_validate(arrival["arrival_plan"]),
        return_plan=ReturnPlan.model_validate(arrival["return_plan"]),
        visit_places=[
            VisitPlaceCandidate(
                resource_id="poi_001",
                destination_id="dest_001",
                area_id="area_001",
                name="示例博物馆",
                address="示例地址一号",
                latitude=30.6595,
                longitude=104.0633,
                categories=["CULTURE", "INDOOR"],
                suggested_duration_minutes=120,
                availability_status="AVAILABLE",
                opening_windows=[TimeWindow(start_at=_at(9), end_at=_at(17))],
                last_entry_at=_at(16, 30),
                physical_intensity="LOW",
                indoor=True,
                weather_sensitivity="LOW",
                planning_fact_ids=["pf_poi_001"],
                evidence_ids=["ev_001"],
            ),
            VisitPlaceCandidate(
                resource_id="poi_002",
                destination_id="dest_001",
                area_id="area_002",
                name="示例公园",
                address="示例地址二号",
                latitude=30.6460,
                longitude=104.0550,
                categories=["NATURE", "OUTDOOR"],
                suggested_duration_minutes=120,
                availability_status="AVAILABLE",
                opening_windows=[TimeWindow(start_at=_at(8), end_at=_at(18))],
                physical_intensity="MEDIUM",
                indoor=False,
                weather_sensitivity="HIGH",
                planning_fact_ids=["pf_poi_002"],
                evidence_ids=["ev_001"],
            ),
        ],
        restaurants=[
            RestaurantCandidate(
                resource_id="restaurant_001",
                destination_id="dest_001",
                area_id="area_001",
                name="示例餐厅",
                address="示例地址三号",
                latitude=30.6480,
                longitude=104.0560,
                cuisine="川菜",
                specialty_dishes=["示例招牌菜"],
                price_per_person=Money(min_amount=60, max_amount=100),
                opening_windows=[TimeWindow(start_at=_at(11), end_at=_at(21))],
                meal_types=["LUNCH", "DINNER"],
                dietary_tags=["辣"],
                route_fit_reason="与博物馆步行范围内",
                planning_fact_ids=["pf_rest_001"],
                evidence_ids=["ev_002"],
            )
        ],
        lodgings=[
            LodgingCandidate(
                resource_id="hotel_001",
                destination_id="dest_001",
                name="示例连锁酒店",
                lodging_type="CHAIN",
                address="示例地址四号",
                lodging_area="示例区域",
                price_range=Money(min_amount=300, max_amount=450),
                commute_summary="到主要活动区域约 30 分钟",
                evidence_ids=["ev_003"],
            )
        ],
        lodging_areas=[
            LodgingAreaCandidate(
                resource_id="area_001",
                destination_id="dest_001",
                name="示例城区",
            ),
            LodgingAreaCandidate(
                resource_id="area_002",
                destination_id="dest_001",
                name="示例公园片区",
            ),
        ],
        evidence=[
            Evidence(
                evidence_id="ev_001",
                entity_id="poi_001",
                entity_type="VISIT_PLACE",
                content="该馆以本地历史文化展陈为主，室内为主，适合雨天。",
                source_type="MOCK",
                source_ref="mock://poi_001",
                collected_at=_NOW,
                acquisition_status="MOCK_ONLY",
                verification_status="PENDING",
            )
        ],
        destination_names={"dest_001": "成都"},
        mock_items=["weather:dest_001"],
    )
    base.update(overrides)
    return GuideContext(**base)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, tzinfo=_NOW.tzinfo)


def _guide(**overrides):
    return compose_travel_guide(
        _plan(),
        _profile(),
        _context(**overrides.pop("context", {})),
        run_mode=overrides.pop("run_mode", RunMode.DEMO),
        **overrides,
    )


def _day(guide, day: date):
    return next(item for item in guide.daily_itinerary if item.date == day)


# --- 七部分与结构 -----------------------------------------------------------


def test_all_seven_sections_are_present() -> None:
    guide = _guide()
    for section in (
        "trip_summary",
        "arrival_and_departure",
        "preparation",
        "lodging",
        "daily_itinerary",
        "budget_and_alternatives",
        "sources_and_freshness",
    ):
        assert getattr(guide, section) is not None


def test_every_plan_day_is_covered() -> None:
    plan, guide = _plan(), _guide()
    expected = {
        plan.start_date + timedelta(days=offset)
        for offset in range((plan.end_date - plan.start_date).days + 1)
    }
    assert {item.date for item in guide.daily_itinerary} == expected


def test_budget_summary_is_passed_through_unchanged() -> None:
    """预算必须来自 CostItem[] 的复算结果，组装层不得自己算一遍。"""

    plan, guide = _plan(), _guide()
    assert guide.budget_and_alternatives.budget_summary == plan.budget_summary


def test_trip_summary_uses_the_destination_name_lookup() -> None:
    guide = _guide()
    assert guide.trip_summary.destination_names == ["成都"]
    assert guide.trip_summary.traveler_count == _profile().traveler_count


def test_trip_summary_falls_back_to_the_raw_id_when_no_name_is_available() -> None:
    guide = _guide(context={"destination_names": {}})
    assert guide.trip_summary.destination_names == ["dest_001"]


# --- 富化规则（与 fixture 对齐）--------------------------------------------


def test_daily_totals_match_the_fixture_arithmetic() -> None:
    guide = _guide()

    arrival_day = _day(guide, date(2026, 10, 2))
    assert arrival_day.total_activity_minutes == 60
    # 当天没有 TravelLeg，通勤时间来自 arrival_plan
    assert arrival_day.total_travel_minutes == 35
    assert arrival_day.estimated_cost.amount == 6

    city_day = _day(guide, date(2026, 10, 3))
    assert city_day.total_activity_minutes == 180
    assert city_day.total_travel_minutes == 25
    # 50（门票单价）+ 60~100（餐厅人均）+ 4（地铁单价）= 114~154
    assert city_day.estimated_cost.amount is None
    assert city_day.estimated_cost.min_amount == 114
    assert city_day.estimated_cost.max_amount == 154

    return_day = _day(guide, date(2026, 10, 5))
    assert return_day.total_travel_minutes == 40  # return_plan.duration_minutes
    assert return_day.estimated_cost.amount == 6


def test_node_cost_prefers_the_referenced_cost_item() -> None:
    guide = _guide()
    node = next(
        item
        for item in _day(guide, date(2026, 10, 3)).nodes
        if item.node_id == "node_001"
    )
    assert node.estimated_cost.amount == 50  # cost_001 的单价，不乘 quantity
    assert node.name == "示例博物馆"
    assert node.address == "示例地址一号"
    assert node.last_entry_at == _at(16, 30)


def test_node_cost_falls_back_to_the_resource_price() -> None:
    guide = _guide()
    node = next(
        item
        for item in _day(guide, date(2026, 10, 3)).nodes
        if item.node_id == "node_002"
    )
    assert node.estimated_cost.min_amount == 60
    assert node.estimated_cost.max_amount == 100
    assert node.name == "示例餐厅"
    assert "招牌菜：示例招牌菜" in node.tips


def test_node_opening_window_is_picked_from_the_matching_window() -> None:
    guide = _guide()
    node = next(
        item
        for item in _day(guide, date(2026, 10, 3)).nodes
        if item.node_id == "node_002"
    )
    assert node.opening_window is not None
    assert node.opening_window.start_at.hour == 11


def test_unknown_cost_is_flagged_instead_of_invented() -> None:
    """既没有 CostItem 也没有资源价格时，明确标未知，不编一个金额。"""

    guide = _guide()
    unknown_day = _day(guide, date(2026, 10, 4))
    assert unknown_day.estimated_cost.amount == 0
    assert any("费用未知" in warning for warning in unknown_day.warnings)
    assert any(
        item.startswith("cost:") for item in guide.sources_and_freshness.unknown_items
    )


def test_plan_node_fields_do_not_leak_into_guide_node() -> None:
    guide = _guide()
    node = _day(guide, date(2026, 10, 3)).nodes[0]
    keys = set(node.model_dump())
    assert {"name", "address", "opening_window", "estimated_cost", "tips"} <= keys
    # 内部对象专有字段不得出现
    assert "cost_item_ids" not in keys
    assert "completed" not in keys


def test_activity_areas_use_area_names_when_available() -> None:
    guide = _guide()
    assert "示例城区" in _day(guide, date(2026, 10, 3)).activity_areas
    assert "示例公园片区" in _day(guide, date(2026, 10, 4)).activity_areas


def test_fake_route_legs_produce_a_warning() -> None:
    guide = _guide()
    warnings = _day(guide, date(2026, 10, 3)).warnings
    assert any("模拟或估算" in warning for warning in warnings)


def test_intensity_levels_are_derived_from_the_schedule() -> None:
    guide = _guide()
    for item in guide.daily_itinerary:
        assert item.intensity_level in ("LOW", "MEDIUM", "HIGH")


def test_stay_segments_and_lodging_candidates_are_linked() -> None:
    guide = _guide()
    assert guide.lodging.stay_segments == list(_plan().stay_segments)
    assert [item.resource_id for item in guide.lodging.primary_candidates] == ["hotel_001"]


def test_evidence_ids_are_collected_into_sources_section() -> None:
    guide = _guide()
    assert "ev_001" in guide.sources_and_freshness.evidence_ids


# --- 缺数据必须明确报错 -----------------------------------------------------


def test_missing_intercity_options_raises_instead_of_faking_a_train() -> None:
    with pytest.raises(GuideCompositionError):
        _guide(context={"intercity_options": []})


def test_missing_arrival_plan_raises() -> None:
    with pytest.raises(GuideCompositionError):
        _guide(context={"arrival_plan": None})


# --- 三类状态分离（ADR-0006）------------------------------------------------


def test_demo_mode_is_never_verified_data() -> None:
    assert (
        derive_data_assurance_status(run_mode=RunMode.DEMO)
        is DataAssuranceStatus.MOCK
    )


def test_verified_mode_with_degraded_items_is_degraded() -> None:
    assert (
        derive_data_assurance_status(
            run_mode=RunMode.VERIFIED, degraded_items=["route:leg_001"]
        )
        is DataAssuranceStatus.DEGRADED
    )


def test_verified_mode_clean_data_is_verified() -> None:
    assert (
        derive_data_assurance_status(run_mode=RunMode.VERIFIED)
        is DataAssuranceStatus.VERIFIED
    )


def test_readiness_requires_a_valid_plan() -> None:
    assert (
        derive_guide_readiness(
            plan_validation_status=PlanValidationStatus.INVALID,
            data_assurance_status=DataAssuranceStatus.VERIFIED,
            run_mode=RunMode.VERIFIED,
            has_error_conflict=False,
            has_warnings=False,
        )
        is GuideReadiness.NOT_READY
    )


def test_readiness_requires_sufficient_data() -> None:
    assert (
        derive_guide_readiness(
            plan_validation_status=PlanValidationStatus.VALID,
            data_assurance_status=DataAssuranceStatus.INSUFFICIENT,
            run_mode=RunMode.VERIFIED,
            has_error_conflict=False,
            has_warnings=False,
        )
        is GuideReadiness.NOT_READY
    )


def test_error_conflict_forces_not_ready() -> None:
    assert (
        derive_guide_readiness(
            plan_validation_status=PlanValidationStatus.VALID,
            data_assurance_status=DataAssuranceStatus.VERIFIED,
            run_mode=RunMode.VERIFIED,
            has_error_conflict=True,
            has_warnings=False,
        )
        is GuideReadiness.NOT_READY
    )


def test_demo_mode_cannot_be_fully_ready() -> None:
    """契约禁止 DEMO 攻略处于 `READY`，所以干净数据也只能是「带警告可读」。"""

    assert (
        derive_guide_readiness(
            plan_validation_status=PlanValidationStatus.VALID,
            data_assurance_status=DataAssuranceStatus.MOCK,
            run_mode=RunMode.DEMO,
            has_error_conflict=False,
            has_warnings=False,
        )
        is GuideReadiness.READY_WITH_WARNINGS
    )


def test_verified_clean_data_can_be_fully_ready() -> None:
    assert (
        derive_guide_readiness(
            plan_validation_status=PlanValidationStatus.VALID,
            data_assurance_status=DataAssuranceStatus.VERIFIED,
            run_mode=RunMode.VERIFIED,
            has_error_conflict=False,
            has_warnings=False,
        )
        is GuideReadiness.READY
    )


def test_composed_demo_guide_is_ready_with_warnings() -> None:
    guide = _guide()
    assert guide.guide_readiness is GuideReadiness.READY_WITH_WARNINGS
    assert guide.data_assurance_status is DataAssuranceStatus.MOCK


def test_contract_rejects_a_demo_guide_claiming_verified_data() -> None:
    """契约自带的守卫必须真的生效，否则「不许声称已验证」只是口号。"""

    with pytest.raises(Exception):
        _guide(data_assurance_status=DataAssuranceStatus.VERIFIED)


def test_conflicts_are_surfaced_in_the_trip_summary() -> None:
    conflict = Conflict(
        conflict_id="conf_001",
        type="BUDGET_EXCEEDED",
        severity="ERROR",
        scope="WHOLE_GUIDE",
        message="最低估算已超出预算上限",
    )
    guide = _guide(context={"conflicts": [conflict]})
    assert "最低估算已超出预算上限" in guide.trip_summary.major_tradeoffs
    assert guide.guide_readiness is GuideReadiness.NOT_READY
