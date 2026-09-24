"""契约枚举集合。

来源：`CONTRACTS.md` v0.3 与 `TRAVEL_GUIDE_SPEC.md` v0.2。

本文件只收录这两份文档中**明确列出完整取值**的枚举。
文档没有列出完整取值集合的字段，例如 `TripProfile.pace`、
`DestinationRequest.priority`、`ResourceCandidate.physical_intensity`、
`PlanState.stage`、`Conflict.type`、`RepairOption.action`，
统一用 `str` 接住，不在此处自行推断；待三人确认后再收紧为枚举。
详见 `docs/contract-open-questions.md`。
"""

from enum import Enum


class ContractEnum(str, Enum):
    """字符串枚举基类：JSON 序列化后即为契约中的大写英文取值。"""

    def __str__(self) -> str:  # pragma: no cover - 仅用于可读输出
        return self.value


# --- TripProfile 相关（CONTRACTS.md §1） -----------------------------------


class BudgetFlexibility(ContractEnum):
    FIXED = "FIXED"
    NEGOTIABLE = "NEGOTIABLE"


class DestinationMode(ContractEnum):
    UNKNOWN = "UNKNOWN"
    SINGLE = "SINGLE"
    MULTIPLE = "MULTIPLE"


# --- 资源与可用性（CONTRACTS.md §5、§6） -----------------------------------


class ResourceType(ContractEnum):
    VISIT_PLACE = "VISIT_PLACE"
    RESTAURANT = "RESTAURANT"
    LODGING = "LODGING"
    LODGING_AREA = "LODGING_AREA"
    TRANSFER_OPTION = "TRANSFER_OPTION"


class AvailabilityStatus(ContractEnum):
    AVAILABLE = "AVAILABLE"
    CONDITIONAL = "CONDITIONAL"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class EntityType(ContractEnum):
    """`Evidence.entity_type` 的取值。

    包含 `ResourceType` 的全部取值，另加两个证据锚点类型：
    `DESTINATION`（目的地资料）与 `ACTIVITY_AREA`（游玩区域资料）。
    这两项为**推断补充**，已在 docs/contract-open-questions.md 中登记。
    """

    DESTINATION = "DESTINATION"
    ACTIVITY_AREA = "ACTIVITY_AREA"
    VISIT_PLACE = "VISIT_PLACE"
    RESTAURANT = "RESTAURANT"
    LODGING = "LODGING"
    LODGING_AREA = "LODGING_AREA"
    TRANSFER_OPTION = "TRANSFER_OPTION"
    INTERCITY_OPTION = "INTERCITY_OPTION"


class SourceType(ContractEnum):
    OFFICIAL = "OFFICIAL"
    AUTHORITY = "AUTHORITY"
    PLATFORM = "PLATFORM"
    GUIDE = "GUIDE"
    MANUAL = "MANUAL"
    DERIVED = "DERIVED"
    MOCK = "MOCK"


class AcquisitionStatus(ContractEnum):
    UNASSESSED = "UNASSESSED"
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    MOCK_ONLY = "MOCK_ONLY"


class VerificationStatus(ContractEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    # REJECTED 的证据不得进入 LLM 上下文（CONTRACTS.md §6）
    REJECTED = "REJECTED"


# --- 交通（CONTRACTS.md §7） -----------------------------------------------


class TravelMode(ContractEnum):
    WALK = "WALK"
    METRO = "METRO"
    BUS = "BUS"
    TAXI = "TAXI"
    BIKE = "BIKE"
    OTHER = "OTHER"


class TravelLegSource(ContractEnum):
    MAP_PROVIDER = "MAP_PROVIDER"
    MANUAL_MATRIX = "MANUAL_MATRIX"
    FAKE = "FAKE"


class IntercityMode(ContractEnum):
    FLIGHT = "FLIGHT"
    HIGH_SPEED_RAIL = "HIGH_SPEED_RAIL"
    TRAIN = "TRAIN"
    BUS = "BUS"
    INTERCITY_METRO = "INTERCITY_METRO"
    SELF_DRIVE = "SELF_DRIVE"


# --- 计划（CONTRACTS.md §8） -----------------------------------------------


class PlanStatus(ContractEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    # OUTDATED 仅用于 TravelGuide，保留在 GuideStatus 中


class GuideStatus(ContractEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    OUTDATED = "OUTDATED"


class NodeType(ContractEnum):
    ARRIVAL = "ARRIVAL"
    CHECK_IN = "CHECK_IN"
    ATTRACTION = "ATTRACTION"
    MEAL = "MEAL"
    REST = "REST"
    WALK_AREA = "WALK_AREA"
    SHOPPING = "SHOPPING"
    TRANSFER = "TRANSFER"
    LODGING = "LODGING"
    FREE_TIME = "FREE_TIME"


class Severity(ContractEnum):
    WARNING = "WARNING"
    # ERROR 不得进入已验证状态（CONTRACTS.md §10）
    ERROR = "ERROR"


# --- 用户动作（CONTRACTS.md §13） ------------------------------------------


class ActionType(ContractEnum):
    SELECT_DESTINATION = "SELECT_DESTINATION"
    CONFIRM_GUIDE = "CONFIRM_GUIDE"
    MODIFY_GUIDE = "MODIFY_GUIDE"
    REPORT_INCIDENT = "REPORT_INCIDENT"


class ChangeType(ContractEnum):
    REMOVE_NODE = "REMOVE_NODE"
    REPLACE_NODE = "REPLACE_NODE"
    ADD_FIXED_NODE = "ADD_FIXED_NODE"
    LOWER_INTENSITY = "LOWER_INTENSITY"
    CHANGE_DATE = "CHANGE_DATE"
    CHANGE_BUDGET = "CHANGE_BUDGET"
    CHANGE_PACE = "CHANGE_PACE"
    CHANGE_LODGING = "CHANGE_LODGING"


class ScopeHint(ContractEnum):
    NODE = "NODE"
    DAY = "DAY"
    STAY_SEGMENT = "STAY_SEGMENT"
    TRIP_SEGMENT = "TRIP_SEGMENT"
    WHOLE_GUIDE = "WHOLE_GUIDE"


# --- TravelGuide 七部分（TRAVEL_GUIDE_SPEC.md §4–§8） ----------------------


class LodgingType(ContractEnum):
    STAR_HOTEL = "STAR_HOTEL"
    CHAIN = "CHAIN"
    LOCAL_FEATURED = "LOCAL_FEATURED"
    HOSTEL = "HOSTEL"
    ECONOMY = "ECONOMY"


class FirstDestinationType(ContractEnum):
    HOTEL = "HOTEL"
    MEAL = "MEAL"
    ACTIVITY = "ACTIVITY"


class PreparationCategory(ContractEnum):
    DOCUMENT = "DOCUMENT"
    BOOKING = "BOOKING"
    CLOTHING = "CLOTHING"
    EQUIPMENT = "EQUIPMENT"
    HEALTH = "HEALTH"
    REFRESH = "REFRESH"


class PreparationTrigger(ContractEnum):
    WEATHER = "WEATHER"
    ACTIVITY = "ACTIVITY"
    TERRAIN = "TERRAIN"
    ALTITUDE = "ALTITUDE"
    TRAVELER = "TRAVELER"
    PLACE = "PLACE"
    GENERAL = "GENERAL"


class PreparationPriority(ContractEnum):
    REQUIRED = "REQUIRED"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"


class AlternativeTrigger(ContractEnum):
    RAIN = "RAIN"
    LATE_START = "LATE_START"
    CLOSURE = "CLOSURE"
    CROWD = "CROWD"
    USER_TIRED = "USER_TIRED"
    RESTAURANT_UNAVAILABLE = "RESTAURANT_UNAVAILABLE"


class CostCategory(ContractEnum):
    INTERCITY = "INTERCITY"
    LODGING = "LODGING"
    LOCAL_TRANSPORT = "LOCAL_TRANSPORT"
    TICKET = "TICKET"
    DINING = "DINING"
    SHOPPING = "SHOPPING"
    OTHER = "OTHER"


class CostStatus(ContractEnum):
    KNOWN = "KNOWN"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"
