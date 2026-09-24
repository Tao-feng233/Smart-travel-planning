from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RunMode(str, Enum):
    DEMO = "DEMO"
    VERIFIED = "VERIFIED"


class PlanValidationStatus(str, Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"


class DataAssuranceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    MOCK = "MOCK"
    INSUFFICIENT = "INSUFFICIENT"


class GuideReadiness(str, Enum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    NOT_READY = "NOT_READY"


class Money(BaseModel):
    amount: float | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "CNY"

    @model_validator(mode="after")
    def validate_shape(self) -> "Money":
        exact = self.amount is not None
        ranged = self.min_amount is not None or self.max_amount is not None
        if exact == ranged:
            raise ValueError("Money must use either amount or min_amount/max_amount")
        if ranged:
            if self.min_amount is None or self.max_amount is None:
                raise ValueError("Money range requires both min_amount and max_amount")
            if self.min_amount > self.max_amount:
                raise ValueError("Money min_amount cannot exceed max_amount")
        return self


class TimeWindow(BaseModel):
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def end_after_start(self) -> "TimeWindow":
        if self.end_at <= self.start_at:
            raise ValueError("TimeWindow end_at must be after start_at")
        return self


class TravelerComposition(BaseModel):
    adults: int = 0
    children: int = 0
    seniors: int = 0


class Constraint(BaseModel):
    constraint_id: str
    kind: Literal["FIXED", "NEGOTIABLE_HARD", "SOFT"]
    field: str
    operator: Literal["EQ", "NE", "LT", "LTE", "GT", "GTE", "IN", "NOT_IN", "CONTAINS"]
    value: Any
    priority: int = 0
    source_text: str | None = None


class DestinationRequest(BaseModel):
    destination_id: str
    name: str
    desired_days: int | None = None
    min_days: int | None = None
    max_days: int | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    fixed: bool = False
    user_reason: str | None = None


class TripProfile(BaseModel):
    session_id: str
    profile_version: int = 1
    departure_city: str
    start_date: date
    end_date: date
    duration_days: int
    timezone: str = "Asia/Shanghai"
    traveler_count: int
    traveler_composition: TravelerComposition
    budget: Money
    budget_flexibility: Literal["FIXED", "NEGOTIABLE"]
    pace: Literal["RELAXED", "BALANCED", "INTENSE"]
    interests: list[str]
    must_visit_resource_ids: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    mobility_constraints: list[str] = Field(default_factory=list)
    dietary_constraints: list[str] = Field(default_factory=list)
    lodging_preferences: list[str] = Field(default_factory=list)
    transport_preferences: list[str] = Field(default_factory=list)
    earliest_day_start: str | None = None
    latest_day_end: str | None = None
    destination_mode: Literal["UNKNOWN", "SINGLE", "MULTIPLE"]
    destination_requests: list[DestinationRequest] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates_and_travelers(self) -> "TripProfile":
        expected = (self.end_date - self.start_date).days + 1
        if expected != self.duration_days:
            raise ValueError("duration_days must equal inclusive start/end date span")
        total = (
            self.traveler_composition.adults
            + self.traveler_composition.children
            + self.traveler_composition.seniors
        )
        if total != self.traveler_count:
            raise ValueError("traveler composition must equal traveler_count")
        return self


class DestinationCoverageSnapshot(BaseModel):
    coverage_snapshot_id: str
    destination_id: str
    coverage_version: str
    category_status: dict[
        str,
        Literal["UNASSESSED", "AVAILABLE", "LIMITED", "UNAVAILABLE", "MOCK_ONLY"],
    ]
    missing_capabilities: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class ReadinessTripContext(BaseModel):
    start_date: date
    end_date: date
    duration_days: int
    traveler_count: int


class PlanningReadinessEvaluation(BaseModel):
    readiness_id: str
    destination_id: str
    trip_profile_version: int
    evaluated_for: ReadinessTripContext
    required_capabilities: list[str]
    failed_requirements: list[str]
    coverage_snapshot_id: str
    ruleset_version: str
    planning_ready: bool
    evaluated_at: datetime

    @model_validator(mode="after")
    def ready_has_no_failed_requirements(self) -> "PlanningReadinessEvaluation":
        if self.planning_ready and self.failed_requirements:
            raise ValueError("planning_ready cannot be true with failed_requirements")
        return self


class FactRecord(BaseModel):
    fact_record_id: str
    entity_id: str
    fact_type: str
    value: Any
    source_type: Literal["OFFICIAL", "AUTHORITY", "PLATFORM", "GUIDE", "MANUAL", "DERIVED", "MOCK"]
    source_ref: str | None = None
    collected_at: datetime
    valid_until: datetime | None = None
    acquisition_status: Literal["UNASSESSED", "AVAILABLE", "LIMITED", "UNAVAILABLE", "MOCK_ONLY"]
    verification_status: Literal["PENDING", "VERIFIED", "REVIEW", "REJECTED"]
    raw_snapshot_ref: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def mock_cannot_be_verified(self) -> "FactRecord":
        if self.source_type == "MOCK" and self.verification_status == "VERIFIED":
            raise ValueError("MOCK FactRecord cannot be VERIFIED")
        return self


class Evidence(BaseModel):
    evidence_id: str
    entity_id: str
    entity_type: str
    content: str
    source_type: Literal["OFFICIAL", "AUTHORITY", "PLATFORM", "GUIDE", "MANUAL", "DERIVED", "MOCK"]
    source_ref: str | None = None
    collected_at: datetime
    valid_until: datetime | None = None
    acquisition_status: Literal["UNASSESSED", "AVAILABLE", "LIMITED", "UNAVAILABLE", "MOCK_ONLY"]
    verification_status: Literal["PENDING", "VERIFIED", "REVIEW", "REJECTED"]
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def mock_cannot_be_verified(self) -> "Evidence":
        if self.source_type == "MOCK" and self.verification_status == "VERIFIED":
            raise ValueError("MOCK Evidence cannot be VERIFIED")
        return self


class PlanningFact(BaseModel):
    planning_fact_id: str
    fact_record_id: str
    entity_id: str
    fact_type: str
    normalized_value: Any
    applies_from: date
    applies_to: date
    assurance: Literal["VERIFIED", "DEGRADED", "MOCK"]


class DataSnapshot(BaseModel):
    data_snapshot_id: str
    created_at: datetime
    run_mode: RunMode
    trip_profile_version: int
    readiness_evaluation_ids: list[str]
    planning_fact_ids: list[str]
    evidence_ids: list[str]
    provider_versions: list[str]
    ruleset_versions: list[str]
    expired_items: list[str]
    degraded_items: list[str]
    mock_items: list[str]
    unknown_items: list[str]


class TripSegment(BaseModel):
    segment_id: str
    destination_id: str
    start_date: date
    end_date: date
    allocated_days: int


class StaySegment(BaseModel):
    stay_segment_id: str
    check_in_date: date
    check_out_date: date
    lodging_id: str
    lodging_area: str
    is_user_booked: bool = False
    locked: bool = False
    switch_reason: str | None = None

    @model_validator(mode="after")
    def checkout_after_checkin(self) -> "StaySegment":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        return self


class PlanNode(BaseModel):
    node_id: str
    node_type: Literal[
        "ARRIVAL", "CHECK_IN", "ATTRACTION", "MEAL", "REST",
        "WALK_AREA", "SHOPPING", "LODGING", "FREE_TIME"
    ]
    resource_id: str | None = None
    start_at: datetime
    end_at: datetime
    cost_item_ids: list[str] = Field(default_factory=list)
    reason: str
    locked: bool = False
    completed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def end_after_start(self) -> "PlanNode":
        if self.end_at <= self.start_at:
            raise ValueError("PlanNode end_at must be after start_at")
        return self


class TravelLeg(BaseModel):
    leg_id: str
    from_node_id: str
    to_node_id: str
    recommended_mode: Literal[
        "WALK", "METRO", "BUS", "TAXI", "BIKE", "RAIL", "FLIGHT", "INTERCITY_BUS", "OTHER"
    ]
    alternative_modes: list[str] = Field(default_factory=list)
    depart_at: datetime
    arrive_at: datetime
    duration_minutes: int
    distance_km: float
    cost_item_ids: list[str] = Field(default_factory=list)
    congestion_note: str | None = None
    walking_burden: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    transfer_count: int = 0
    reason: str
    source: Literal["MAP_PROVIDER", "MANUAL_MATRIX", "FAKE"]
    is_estimated: bool


class DayPlan(BaseModel):
    date: date
    segment_id: str
    stay_segment_id: str
    node_ids: list[str]
    travel_leg_ids: list[str]


class CostItem(BaseModel):
    cost_item_id: str
    category: Literal[
        "INTERCITY", "LODGING", "LOCAL_TRANSPORT", "TICKET", "DINING", "SHOPPING", "OTHER"
    ]
    item_ref: str
    unit_price: Money
    quantity: float = 1
    pricing_scope: Literal["PER_PERSON", "PER_GROUP", "PER_ROOM", "PER_NIGHT", "PER_ITEM"]
    status: Literal["KNOWN", "ESTIMATED", "UNKNOWN"]
    paid: bool = False
    refundable: bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_quantity(self) -> "CostItem":
        if self.quantity <= 0:
            raise ValueError("CostItem quantity must be positive")
        return self


class BudgetSummary(BaseModel):
    currency: str
    total_limit: float
    known_total: float
    estimated_min_total: float
    estimated_max_total: float
    remaining_min: float
    remaining_max: float
    by_category: dict[str, float]
    unknown_cost_item_ids: list[str]


class IntercityOption(BaseModel):
    option_id: str
    mode: Literal["FLIGHT", "HIGH_SPEED_RAIL", "TRAIN", "BUS", "INTERCITY_METRO", "SELF_DRIVE"]
    origin_station: str
    destination_station: str
    departure_window: TimeWindow
    arrival_window: TimeWindow
    door_to_door_minutes: int
    price_range: Money
    transfer_count: int = 0
    baggage_note: str | None = None
    booking_required: bool = False
    booking_advice: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ArrivalPlan(BaseModel):
    station: str
    first_destination_type: Literal["LODGING", "MEAL", "ACTIVITY"]
    first_destination_id: str
    local_transport_mode: Literal["WALK", "METRO", "BUS", "TAXI", "OTHER"]
    duration_minutes: int
    estimated_cost: Money
    reason: str


class ReturnPlan(BaseModel):
    origin_id: str
    departure_station: str
    local_transport_mode: Literal["WALK", "METRO", "BUS", "TAXI", "OTHER"]
    recommended_leave_at: datetime
    duration_minutes: int
    estimated_cost: Money
    reason: str


class PreparationItem(BaseModel):
    item_id: str
    category: Literal["DOCUMENT", "BOOKING", "CLOTHING", "EQUIPMENT", "HEALTH", "REFRESH"]
    title: str
    description: str
    trigger_type: Literal["WEATHER", "ACTIVITY", "PLACE", "TRAVELER", "GENERAL"]
    trigger_ref: str | None = None
    priority: Literal["REQUIRED", "RECOMMENDED", "OPTIONAL"]
    due_at: datetime | None = None
    reason: str
    completed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class LodgingCandidate(BaseModel):
    lodging_id: str
    name: str
    lodging_type: Literal["STAR_HOTEL", "CHAIN", "LOCAL_FEATURED", "HOSTEL", "ECONOMY"]
    address: str
    lodging_area: str
    price_range: Money
    rating: float | None = None
    review_count: int | None = None
    quality_flags: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    commute_summary: str
    suitable_for: list[str] = Field(default_factory=list)
    unsuitable_for: list[str] = Field(default_factory=list)
    booking_url: str | None = None
    availability_is_realtime: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class VisitPlaceCandidate(BaseModel):
    resource_id: str
    resource_type: Literal["VISIT_PLACE"] = "VISIT_PLACE"
    destination_id: str
    area_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    categories: list[str]
    suggested_duration_minutes: int
    availability_status: Literal["AVAILABLE", "CONDITIONAL", "UNAVAILABLE", "UNKNOWN"]
    opening_windows: list[TimeWindow]
    last_entry_at: datetime | None = None
    reservation_required: bool = False
    physical_intensity: Literal["LOW", "MEDIUM", "HIGH"]
    indoor: bool
    weather_sensitivity: Literal["LOW", "MEDIUM", "HIGH"]
    planning_fact_ids: list[str]
    evidence_ids: list[str]


class RestaurantCandidate(BaseModel):
    resource_id: str
    resource_type: Literal["RESTAURANT"] = "RESTAURANT"
    destination_id: str
    area_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    cuisine: str
    specialty_dishes: list[str]
    price_per_person: Money
    opening_windows: list[TimeWindow]
    meal_types: list[str]
    dietary_tags: list[str]
    spicy_level: str | None = None
    reservation_required: bool = False
    queue_note: str | None = None
    rating: float | None = None
    review_count: int | None = None
    route_fit_reason: str
    planning_fact_ids: list[str]
    evidence_ids: list[str]


class PreparationRule(BaseModel):
    rule_id: str
    trigger_type: Literal["WEATHER", "ACTIVITY", "TERRAIN", "ALTITUDE", "TRAVELER", "PLACE"]
    trigger_condition: dict[str, Any]
    category: Literal["DOCUMENT", "BOOKING", "CLOTHING", "EQUIPMENT", "HEALTH", "REFRESH"]
    item_name: str
    instruction: str
    priority: Literal["REQUIRED", "RECOMMENDED", "OPTIONAL"]
    due_at: datetime | None = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class GuideNode(BaseModel):
    node_id: str
    node_type: str
    resource_id: str | None = None
    name: str
    address: str | None = None
    start_at: datetime
    end_at: datetime
    opening_window: TimeWindow | None = None
    last_entry_at: datetime | None = None
    reservation_required: bool = False
    estimated_cost: Money
    reason: str
    tips: list[str] = Field(default_factory=list)
    locked: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class GuideDay(BaseModel):
    date: date
    day_theme: str
    activity_areas: list[str]
    start_location: str
    end_location: str
    nodes: list[GuideNode]
    travel_legs: list[TravelLeg]
    total_activity_minutes: int
    total_travel_minutes: int
    intensity_level: Literal["LOW", "MEDIUM", "HIGH"]
    estimated_cost: Money
    warnings: list[str] = Field(default_factory=list)
    alternative_plan_ids: list[str] = Field(default_factory=list)


class AlternativePlan(BaseModel):
    alternative_plan_id: str
    trigger: Literal["RAIN", "LATE_START", "CLOSURE", "CROWD", "USER_TIRED", "RESTAURANT_UNAVAILABLE"]
    affected_node_ids: list[str]
    replacement_resource_ids: list[str]
    cost_delta: Money
    time_delta_minutes: int
    reason: str
    requires_user_confirmation: bool


class TripSummarySection(BaseModel):
    destination_names: list[str]
    start_date: date
    end_date: date
    duration_days: int
    traveler_count: int
    overall_theme: str
    overall_reason: str
    major_tradeoffs: list[str] = Field(default_factory=list)


class ArrivalAndDepartureSection(BaseModel):
    recommended_option: IntercityOption
    alternative_options: list[IntercityOption] = Field(default_factory=list)
    arrival_plan: ArrivalPlan
    return_plan: ReturnPlan


class PreparationSection(BaseModel):
    items: list[PreparationItem]
    refresh_before_departure: list[PreparationItem] = Field(default_factory=list)


class LodgingSection(BaseModel):
    stay_segments: list[StaySegment]
    primary_candidates: list[LodgingCandidate]
    alternative_candidates: list[LodgingCandidate] = Field(default_factory=list)


class BudgetAndAlternativesSection(BaseModel):
    budget_summary: BudgetSummary
    alternative_plans: list[AlternativePlan] = Field(default_factory=list)


class SourcesAndFreshnessSection(BaseModel):
    fact_record_ids: list[str]
    evidence_ids: list[str]
    degraded_items: list[str]
    mock_items: list[str]
    unknown_items: list[str]
    last_updated: datetime


class ItineraryPlan(BaseModel):
    plan_id: str
    plan_version: int
    parent_plan_version: int | None = None
    session_id: str
    timezone: str
    start_date: date
    end_date: date
    trip_segments: list[TripSegment]
    stay_segments: list[StaySegment]
    days: list[DayPlan]
    nodes: list[PlanNode]
    travel_legs: list[TravelLeg]
    cost_items: list[CostItem]
    budget_summary: BudgetSummary
    plan_validation_status: PlanValidationStatus
    conflict_ids: list[str]
    data_snapshot_id: str

    @model_validator(mode="after")
    def validate_plan_integrity(self) -> "ItineraryPlan":
        expected_dates: set[date] = set()
        current = self.start_date
        while current <= self.end_date:
            expected_dates.add(current)
            current += timedelta(days=1)
        actual_dates = {day.date for day in self.days}
        if actual_dates != expected_dates:
            raise ValueError("DayPlan dates must cover the complete inclusive trip range")

        node_map = {node.node_id: node for node in self.nodes}
        if len(node_map) != len(self.nodes):
            raise ValueError("PlanNode IDs must be unique")
        leg_map = {leg.leg_id: leg for leg in self.travel_legs}
        if len(leg_map) != len(self.travel_legs):
            raise ValueError("TravelLeg IDs must be unique")

        for day in self.days:
            if not set(day.node_ids).issubset(node_map):
                raise ValueError("DayPlan references unknown node IDs")
            if not set(day.travel_leg_ids).issubset(leg_map):
                raise ValueError("DayPlan references unknown travel leg IDs")

        for leg in self.travel_legs:
            if leg.from_node_id not in node_map or leg.to_node_id not in node_map:
                raise ValueError("TravelLeg references unknown nodes")
            if leg.arrive_at <= leg.depart_at:
                raise ValueError("TravelLeg arrive_at must be after depart_at")
            actual_minutes = int((leg.arrive_at - leg.depart_at).total_seconds() / 60)
            if actual_minutes != leg.duration_minutes:
                raise ValueError("TravelLeg duration_minutes must match timestamps")

        for day in expected_dates:
            day_nodes = sorted(
                [node for node in self.nodes if node.start_at.date() == day],
                key=lambda node: node.start_at,
            )
            for previous, following in zip(day_nodes, day_nodes[1:]):
                if following.start_at < previous.end_at:
                    raise ValueError("PlanNodes cannot overlap")

        known_total = 0.0
        estimated_min = 0.0
        estimated_max = 0.0
        unknown_ids: list[str] = []
        for item in self.cost_items:
            money = item.unit_price
            if item.status == "UNKNOWN":
                unknown_ids.append(item.cost_item_id)
                continue
            if money.amount is not None:
                minimum = maximum = money.amount * item.quantity
            else:
                minimum = float(money.min_amount) * item.quantity
                maximum = float(money.max_amount) * item.quantity
            if item.status == "KNOWN":
                if minimum != maximum:
                    raise ValueError("KNOWN CostItem must use an exact amount")
                known_total += minimum
            else:
                estimated_min += minimum
                estimated_max += maximum

        calculated_min = known_total + estimated_min
        calculated_max = known_total + estimated_max
        tolerance = 0.01
        if abs(self.budget_summary.known_total - known_total) > tolerance:
            raise ValueError("BudgetSummary known_total does not match CostItem[]")
        if abs(self.budget_summary.estimated_min_total - calculated_min) > tolerance:
            raise ValueError("BudgetSummary estimated_min_total does not match CostItem[]")
        if abs(self.budget_summary.estimated_max_total - calculated_max) > tolerance:
            raise ValueError("BudgetSummary estimated_max_total does not match CostItem[]")
        if sorted(self.budget_summary.unknown_cost_item_ids) != sorted(unknown_ids):
            raise ValueError("BudgetSummary unknown_cost_item_ids does not match CostItem[]")
        if (
            self.plan_validation_status == PlanValidationStatus.VALID
            and self.budget_summary.estimated_min_total > self.budget_summary.total_limit
        ):
            raise ValueError("VALID plan cannot exceed budget at the minimum estimate")
        return self


class TravelGuide(BaseModel):
    guide_id: str
    guide_version: int
    parent_guide_version: int | None = None
    session_id: str
    run_mode: RunMode
    lifecycle_status: Literal["DRAFT", "CONFIRMED", "EXECUTING", "COMPLETED", "OUTDATED"]
    plan_validation_status: PlanValidationStatus
    data_assurance_status: DataAssuranceStatus
    guide_readiness: GuideReadiness
    timezone: str
    trip_summary: TripSummarySection
    arrival_and_departure: ArrivalAndDepartureSection
    preparation: PreparationSection
    lodging: LodgingSection
    daily_itinerary: list[GuideDay]
    budget_and_alternatives: BudgetAndAlternativesSection
    sources_and_freshness: SourcesAndFreshnessSection
    plan_id: str
    plan_version: int
    data_snapshot_id: str

    @model_validator(mode="after")
    def validate_publication_state(self) -> "TravelGuide":
        if self.plan_validation_status == PlanValidationStatus.INVALID:
            if self.guide_readiness != GuideReadiness.NOT_READY:
                raise ValueError("Invalid plan must produce NOT_READY guide")
        if self.data_assurance_status == DataAssuranceStatus.INSUFFICIENT:
            if self.guide_readiness != GuideReadiness.NOT_READY:
                raise ValueError("Insufficient data must produce NOT_READY guide")
        if self.run_mode == RunMode.DEMO:
            if self.data_assurance_status == DataAssuranceStatus.VERIFIED:
                raise ValueError("DEMO guide cannot claim VERIFIED data assurance")
            if self.guide_readiness == GuideReadiness.READY:
                raise ValueError("DEMO guide must be READY_WITH_WARNINGS or NOT_READY")
        return self


MODEL_REGISTRY = {
    "TripProfile": TripProfile,
    "ItineraryPlan": ItineraryPlan,
    "TravelGuide": TravelGuide,
    "Money": Money,
    "DestinationCoverageSnapshot": DestinationCoverageSnapshot,
    "PlanningReadinessEvaluation": PlanningReadinessEvaluation,
    "FactRecord": FactRecord,
    "Evidence": Evidence,
    "PlanningFact": PlanningFact,
    "DataSnapshot": DataSnapshot,
}
