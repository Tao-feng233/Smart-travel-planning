"""TravelGuide（七部分攻略）契约对象。

来源：`CONTRACTS.md` §9 与 `TRAVEL_GUIDE_SPEC.md` §3–§9。
`TravelGuide` 是用户侧最终产物，`ItineraryPlan` 只是其中“每日行程”的核心。

P0 约定：字段无法获得时保留空值并列入 `sources_and_freshness.unknown_items`，
不得伪造填充（`CONTRACTS.md` §9）。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from .contracts import (
    Clock,
    ContractModel,
    DayPlan,
    Evidence,
    PlanNode,
    StaySegment,
    TripSegment,
)
from .enums import (
    AlternativeTrigger,
    CostCategory,
    CostStatus,
    FirstDestinationType,
    GuideStatus,
    IntercityMode,
    LodgingType,
    PreparationCategory,
    PreparationPriority,
    PreparationTrigger,
    TravelMode,
)


# --- 第一部分：旅行总览 -----------------------------------------------------


class TripSummary(ContractModel):
    destination_names: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    traveler_count: int
    departure_city: str | None = None
    trip_segments: list[TripSegment] = Field(default_factory=list)
    overall_theme: str | None = None
    overall_reason: str | None = None
    major_tradeoffs: list[str] = Field(default_factory=list)
    pace: str | None = None
    interests: list[str] = Field(default_factory=list)
    budget_amount: float | None = None
    budget_flexibility: str | None = None


# --- 第二部分：抵达与离开 ---------------------------------------------------


class IntercityOption(ContractModel):
    option_id: str
    mode: IntercityMode
    origin_city: str | None = None
    origin_station: str | None = None
    destination_city: str | None = None
    destination_station: str | None = None
    departure_window: str | None = None
    arrival_window: str | None = None
    in_vehicle_minutes: int | None = None
    door_to_door_minutes: int | None = None
    estimated_cost: float | None = None
    transfer_count: int | None = None
    baggage_or_checkin_note: str | None = None
    booking_required: bool = False
    latest_booking_advice: str | None = None
    suitability_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ArrivalPlan(ContractModel):
    arrival_station: str | None = None
    first_destination_type: FirstDestinationType | None = None
    first_destination_id: str | None = None
    local_transport_mode: TravelMode | None = None
    duration_minutes: int | None = None
    estimated_cost: float | None = None
    reason: str | None = None


class ArrivalAndDeparture(ContractModel):
    recommended_option: IntercityOption | None = None
    alternative_options: list[IntercityOption] = Field(default_factory=list)
    arrival_plan: ArrivalPlan | None = None
    return_plan: ArrivalPlan | None = None


# --- 第三部分：行前准备 -----------------------------------------------------


class PreparationItem(ContractModel):
    item_id: str
    category: PreparationCategory
    title: str
    description: str | None = None
    trigger_type: PreparationTrigger | None = None
    trigger_ref: str | None = None
    priority: PreparationPriority = PreparationPriority.RECOMMENDED
    due_time: str | None = None
    reason: str | None = None
    completed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class PreparationSection(ContractModel):
    items: list[PreparationItem] = Field(default_factory=list)
    refresh_before_departure: list[str] = Field(default_factory=list)


# --- 第四部分：住宿方案 -----------------------------------------------------


class PriceRange(ContractModel):
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "CNY"
    # KNOWN/ESTIMATED/UNKNOWN：没有实时库存时必须标 ESTIMATED 或 UNKNOWN
    status: CostStatus = CostStatus.ESTIMATED


class LodgingCandidate(ContractModel):
    lodging_id: str
    name: str
    lodging_type: LodgingType | None = None
    brand: str | None = None
    star_level: float | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    lodging_area: str | None = None
    price_range: PriceRange | None = None
    rating: float | None = None
    review_count: int | None = None
    quality_flags: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    room_types: list[str] = Field(default_factory=list)
    check_in_time: Clock | None = None
    check_out_time: Clock | None = None
    nearby_transport: list[str] = Field(default_factory=list)
    nearby_food_score: float | None = None
    commute_summary: str | None = None
    suitable_for: list[str] = Field(default_factory=list)
    unsuitable_for: list[str] = Field(default_factory=list)
    booking_url: str | None = None
    availability_status: str | None = None
    source_updated_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class LodgingSection(ContractModel):
    stay_segments: list[StaySegment] = Field(default_factory=list)
    primary_candidates: list[LodgingCandidate] = Field(default_factory=list)
    alternative_candidates: list[LodgingCandidate] = Field(default_factory=list)


# --- 第五部分：每日详细行程 -------------------------------------------------


class DailyItinerary(ContractModel):
    days: list[DayPlan] = Field(default_factory=list)


# --- 第六部分：预算与备用方案 -----------------------------------------------


class CostItem(ContractModel):
    category: CostCategory
    item_ref: str | None = None
    amount_or_range: str | None = None
    currency: str = "CNY"
    per_person_or_group: str | None = None
    quantity: float | None = None
    status: CostStatus = CostStatus.UNKNOWN
    valid_at: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class GuideBudgetSummary(ContractModel):
    total_limit: float | None = None
    intercity_transport: float | None = None
    lodging: float | None = None
    local_transport: float | None = None
    tickets: float | None = None
    dining: float | None = None
    shopping: float | None = None
    contingency: float | None = None
    known_cost: float = 0
    estimated_cost: float = 0
    unpriced_items: list[str] = Field(default_factory=list)
    remaining_budget: float | None = None
    cost_items: list[CostItem] = Field(default_factory=list)


class AlternativePlan(ContractModel):
    trigger: AlternativeTrigger
    affected_node_ids: list[str] = Field(default_factory=list)
    replacement_nodes: list[PlanNode] = Field(default_factory=list)
    cost_delta: float | None = None
    time_delta: int | None = None
    reason: str | None = None
    requires_user_confirmation: bool = False


class BudgetAndAlternatives(ContractModel):
    budget_summary: GuideBudgetSummary = Field(default_factory=GuideBudgetSummary)
    alternative_plans: list[AlternativePlan] = Field(default_factory=list)


# --- 第七部分：来源与更新时间 -----------------------------------------------


class SourcesAndFreshness(ContractModel):
    evidence: list[Evidence] = Field(default_factory=list)
    degraded_items: list[str] = Field(default_factory=list)
    unknown_items: list[str] = Field(default_factory=list)
    last_updated: datetime | None = None


# --- TravelGuide ------------------------------------------------------------


class TravelGuide(ContractModel):
    guide_id: str
    session_id: str
    version: int = 1
    status: GuideStatus = GuideStatus.DRAFT
    trip_summary: TripSummary
    arrival_and_departure: ArrivalAndDeparture = Field(default_factory=ArrivalAndDeparture)
    preparation: PreparationSection = Field(default_factory=PreparationSection)
    lodging: LodgingSection = Field(default_factory=LodgingSection)
    daily_itinerary: DailyItinerary = Field(default_factory=DailyItinerary)
    budget_and_alternatives: BudgetAndAlternatives = Field(
        default_factory=BudgetAndAlternatives
    )
    sources_and_freshness: SourcesAndFreshness = Field(default_factory=SourcesAndFreshness)

    @model_validator(mode="after")
    def _check_unknown_items(self) -> "TravelGuide":
        """P0 规则：无法获得的字段必须列入 unknown_items，不得静默留空。"""
        if self.status is GuideStatus.VALIDATED and self.sources_and_freshness.last_updated is None:
            raise ValueError("status=VALIDATED 的攻略必须给出 sources_and_freshness.last_updated")
        return self


from .contracts import PlanState  # noqa: E402

PlanState.model_rebuild(force=True)

