"""核心契约对象。

来源：`CONTRACTS.md` v0.3 第 1–13 节。字段名、枚举取值与示例 JSON 一一对应。

设计约定：

1. 所有契约对象继承 `ContractModel`，默认禁止未声明字段。
   这对应 `AGENTS.md` 的协作检查项“是否偷偷新增字段”：任何模块多传一个
   契约里没有的键，都会在进入工作流的第一步就抛 `ValidationError`。
2. 时间点字段（如 `09:30`）使用 ``HH:MM`` 字符串而非 `datetime.time`，
   以保证序列化结果与契约示例逐字一致，不出现多余的 `:00` 秒。
3. 日期字段使用 `datetime.date`，时间戳字段使用带时区的 `datetime`。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints, model_validator

from .enums import (
    AcquisitionStatus,
    ActionType,
    AvailabilityStatus,
    BudgetFlexibility,
    ChangeType,
    DestinationMode,
    EntityType,
    NodeType,
    PlanStatus,
    ResourceType,
    ScopeHint,
    Severity,
    SourceType,
    TravelLegSource,
    TravelMode,
    VerificationStatus,
)

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """所有契约对象的基类：禁止契约之外的字段。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
"""``HH:MM`` 形式的时刻，例如 ``09:30``。"""


# --- §1 TripProfile ---------------------------------------------------------


class TravelerComposition(ContractModel):
    adults: int = 0
    children: int = 0
    seniors: int = 0


class Budget(ContractModel):
    amount: float
    currency: str = "CNY"
    flexibility: BudgetFlexibility = BudgetFlexibility.NEGOTIABLE


class DestinationRequest(ContractModel):
    destination_id: str
    name: str
    desired_days: int | None = None
    min_days: int | None = None
    max_days: int | None = None
    # 契约只给出示例值 HIGH，未列出完整取值集合，暂用 str 接住
    priority: str = "MEDIUM"
    fixed: bool = False
    user_reason: str | None = None


class TripProfile(ContractModel):
    """旅行画像：从旅行请求及后续回答中整理出的**当前**有效需求集合。

    `CONTEXT.md` 明确该对象“会随着对话持续更新”，且本对象自带
    `missing_fields` 字段——只有允许画像在补全过程中存在，这个字段才有意义。
    因此除 `session_id` 外，可缺失的字段一律允许为 `None`，
    由 `missing_fields` 记录当前还缺什么。
    `CONTRACTS.md` §1 的示例 JSON 表示的是“信息已齐全”的终态。

    该解释已登记到 `docs/contract-open-questions.md`，待三人确认后写回契约。
    """

    session_id: str
    departure_city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    traveler_count: int | None = None
    traveler_composition: TravelerComposition | None = None
    mobility_constraints: list[str] = Field(default_factory=list)
    budget: Budget | None = None
    # 契约只给出示例值 RELAXED，未列出完整取值集合，暂用 str 接住
    pace: str | None = None
    interests: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    fixed_facts: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    destination_mode: DestinationMode = DestinationMode.UNKNOWN
    destination_requests: list[DestinationRequest] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_dates(self) -> "TripProfile":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date 不得早于 start_date")
        return self

    @property
    def duration_days(self) -> int | None:
        """旅行总天数（含首尾两天）；日期未确定时返回 None。"""
        if self.start_date is None or self.end_date is None:
            return None
        return (self.end_date - self.start_date).days + 1


# --- §2 KnowledgeCoverage ---------------------------------------------------


class KnowledgeCoverage(ContractModel):
    destination_id: str
    coverage_version: str
    destination_profile_status: AcquisitionStatus = AcquisitionStatus.UNASSESSED
    visit_place_count: int = 0
    visit_place_fact_coverage: float = 0.0
    opening_rule_coverage: float = 0.0
    route_coverage: float = 0.0
    lodging_coverage: float = 0.0
    restaurant_coverage: float = 0.0
    intercity_transport_coverage: float = 0.0
    preparation_rule_coverage: float = 0.0
    missing_capabilities: list[str] = Field(default_factory=list)
    planning_ready: bool = False
    evaluated_at: datetime | None = None


# --- §4 DestinationRecommendation ------------------------------------------


class DestinationRecommendation(ContractModel):
    destination_id: str
    suggested_days: int
    coverage_version: str
    suitable: bool = True
    reason: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


# --- §5 ResourceCandidate ---------------------------------------------------


class TimeWindow(ContractModel):
    start: Clock
    end: Clock

    @model_validator(mode="after")
    def _check_order(self) -> "TimeWindow":
        if self.end <= self.start:
            raise ValueError("TimeWindow.end 必须晚于 start")
        return self


class ResourceAvailability(ContractModel):
    status: AvailabilityStatus
    valid_dates: list[date] = Field(default_factory=list)
    time_windows: list[TimeWindow] = Field(default_factory=list)
    reservation_required: bool = False
    reason: str | None = None


class ResourceCandidate(ContractModel):
    resource_id: str
    resource_type: ResourceType
    destination_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    categories: list[str] = Field(default_factory=list)
    suggested_duration_minutes: int | None = None
    estimated_cost: float | None = None
    availability: ResourceAvailability
    # 契约示例值为 LOW，未列出完整取值集合，暂用 str 接住
    physical_intensity: str | None = None
    weather_sensitivity: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_updated_at: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def _check_availability_rules(self) -> "ResourceCandidate":
        # UNAVAILABLE 资源不得进入计划；这里只做数据层面的显式提醒，
        # 真正的前置过滤在 C3 filter_availability 节点完成。
        if (
            self.availability.status is AvailabilityStatus.UNAVAILABLE
            and not self.availability.reason
        ):
            raise ValueError("UNAVAILABLE 资源必须给出 availability.reason")
        return self


# --- §6 Evidence ------------------------------------------------------------


class Evidence(ContractModel):
    evidence_id: str
    entity_id: str
    entity_type: EntityType
    content: str
    source_type: SourceType
    source_ref: str
    collected_at: datetime
    valid_until: datetime | None = None
    acquisition_status: AcquisitionStatus = AcquisitionStatus.UNASSESSED
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @model_validator(mode="after")
    def _check_verification(self) -> "Evidence":
        if self.verification_status is VerificationStatus.REJECTED:
            # REJECTED 的证据不得进入 LLM 上下文，也不应被组装进攻略
            raise ValueError("verification_status=REJECTED 的证据不得进入契约对象")
        if self.source_type is SourceType.MOCK and self.acquisition_status is not (
            AcquisitionStatus.MOCK_ONLY
        ):
            raise ValueError("source_type=MOCK 时必须同时标记 acquisition_status=MOCK_ONLY")
        return self


# --- §7 TravelLeg -----------------------------------------------------------


class TravelLeg(ContractModel):
    leg_id: str
    from_node_id: str
    to_node_id: str
    recommended_mode: TravelMode
    alternative_modes: list[TravelMode] = Field(default_factory=list)
    depart_time: Clock | None = None
    arrive_time: Clock | None = None
    duration_minutes: int
    distance_km: float | None = None
    estimated_cost: float | None = None
    congestion_note: str | None = None
    # 契约示例值为 LOW，未列出完整取值集合，暂用 str 接住
    walking_burden: str | None = None
    transfer_count: int | None = None
    reason: str | None = None
    source: TravelLegSource
    is_estimated: bool = False


# --- §8 ItineraryPlan -------------------------------------------------------


class TripSegment(ContractModel):
    segment_id: str
    destination_id: str
    start_date: date
    end_date: date
    allocated_days: int

    @model_validator(mode="after")
    def _check_dates(self) -> "TripSegment":
        if self.end_date < self.start_date:
            raise ValueError("TripSegment.end_date 不得早于 start_date")
        return self


class StaySegment(ContractModel):
    stay_segment_id: str
    start_date: date
    end_date: date
    lodging_id: str | None = None
    lodging_area: str | None = None
    is_user_booked: bool = False
    locked: bool = False
    switch_reason: str | None = None


class PlanNode(ContractModel):
    node_id: str
    node_type: NodeType
    resource_id: str | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    duration_minutes: int | None = None
    address: str | None = None
    opening_window: str | None = None
    last_entry_time: Clock | None = None
    reservation_required: bool = False
    estimated_cost: float | None = None
    reason: str | None = None
    tips: list[str] = Field(default_factory=list)
    locked: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class DayPlan(ContractModel):
    date: date
    segment_id: str
    stay_segment_id: str | None = None
    day_theme: str | None = None
    activity_areas: list[str] = Field(default_factory=list)
    start_location: str | None = None
    end_location: str | None = None
    nodes: list[PlanNode] = Field(default_factory=list)
    travel_legs: list[TravelLeg] = Field(default_factory=list)
    total_activity_minutes: int | None = None
    total_travel_minutes: int | None = None
    # 契约示例值为 LOW，未列出完整取值集合，暂用 str 接住
    intensity_level: str | None = None
    estimated_cost: float | None = None
    warnings: list[str] = Field(default_factory=list)
    backup_nodes: list[PlanNode] = Field(default_factory=list)


class PlanBudget(ContractModel):
    known_cost: float = 0
    estimated_cost: float = 0
    unpriced_items: list[str] = Field(default_factory=list)


class ItineraryPlan(ContractModel):
    plan_id: str
    session_id: str
    version: int = 1
    status: PlanStatus = PlanStatus.DRAFT
    segments: list[TripSegment] = Field(default_factory=list)
    stay_segments: list[StaySegment] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)
    budget: PlanBudget = Field(default_factory=PlanBudget)
    warnings: list[str] = Field(default_factory=list)
    data_snapshot_id: str | None = None


# --- §10 Conflict -----------------------------------------------------------


class RepairOption(ContractModel):
    # 契约示例值为 REORDER_NODES，未列出完整取值集合，暂用 str 接住
    action: str
    description: str
    requires_user_confirmation: bool = False


class Conflict(ContractModel):
    conflict_id: str
    # 契约示例值为 TIME_WINDOW，未列出完整取值集合，暂用 str 接住
    type: str
    severity: Severity
    # 契约示例值为 DAY，未列出完整取值集合，暂用 str 接住
    scope: str
    message: str
    affected_node_ids: list[str] = Field(default_factory=list)
    repair_options: list[RepairOption] = Field(default_factory=list)


# --- §11 PlanState ----------------------------------------------------------


class PlanState(ContractModel):
    """LangGraph 的会话状态。

    注意：契约示例中 `profile`、`current_plan`、`current_guide` 写作 `{}`，
    表示“尚未产生”，本模型用 `None` 表达同一语义。
    """

    session_id: str
    # 契约示例值为 VALIDATING，未列出完整取值集合，暂用 str 接住
    stage: str
    profile: TripProfile | None = None
    destination_candidates: list[DestinationRecommendation] = Field(default_factory=list)
    resource_candidates: list[ResourceCandidate] = Field(default_factory=list)
    current_plan: ItineraryPlan | None = None
    current_guide: "TravelGuide | None" = None
    conflicts: list[Conflict] = Field(default_factory=list)
    locked_node_ids: list[str] = Field(default_factory=list)
    completed_node_ids: list[str] = Field(default_factory=list)
    change_history: list[dict[str, Any]] = Field(default_factory=list)
    data_snapshot_id: str | None = None
    repair_attempts: int = 0
    awaiting_user_input: bool = False


# --- §13 UserAction / ChangeRequest -----------------------------------------


class ChangeRequestPayload(ContractModel):
    change_type: ChangeType
    scope_hint: ScopeHint
    day_date: date | None = None
    target_node_ids: list[str] = Field(default_factory=list)


class UserAction(ContractModel):
    action_type: ActionType
    session_id: str
    guide_id: str | None = None
    raw_text: str
    payload: ChangeRequestPayload | None = None

    @model_validator(mode="after")
    def _check_payload(self) -> "UserAction":
        if self.action_type is ActionType.MODIFY_GUIDE and self.payload is None:
            raise ValueError("action_type=MODIFY_GUIDE 时必须提供 payload(ChangeRequest)")
        return self


# `PlanState.current_guide` 指向 `TravelGuide`，该类型定义在 `guide.py`。
# 为避免循环导入，这里只保留前向引用，rebuild 由 `schemas/__init__.py`
# 和 `guide.py` 在两者都加载完成后统一触发。
