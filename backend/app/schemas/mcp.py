"""旅游 MCP Server 的工具输入/输出契约。

来源：`CONTRACTS.md` §12。C 的 LangGraph 节点通过 MCP Client 调用这些工具，
A 的 MCP Server 实现这些工具。两侧共用本文件的模型，避免参数口径漂移。

契约只规定了字段名，未固定嵌套结构的部分（`travel_dates`、
`temperature_range`）在此做最小推断，已登记到
`docs/contract-open-questions.md`。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .contracts import Clock, ContractModel, Evidence, KnowledgeCoverage, ResourceCandidate, TimeWindow
from .enums import AvailabilityStatus, ResourceType, SourceType, TravelLegSource, TravelMode


class DateRange(ContractModel):
    start_date: date
    end_date: date


# --- search_planning_ready_destinations ------------------------------------


class SearchPlanningReadyDestinationsInput(ContractModel):
    query: str
    travel_dates: DateRange | None = None
    duration_days: int | None = None
    traveler_constraints: list[str] = Field(default_factory=list)
    top_k: int = 5


class PlanningReadyDestination(ContractModel):
    destination_id: str
    name: str
    coverage_version: str
    planning_ready: bool = False
    coverage: KnowledgeCoverage | None = None


class SearchPlanningReadyDestinationsOutput(ContractModel):
    candidates: list[PlanningReadyDestination] = Field(default_factory=list)


# --- search_travel_knowledge ------------------------------------------------


class SearchTravelKnowledgeInput(ContractModel):
    query: str
    province: str | None = None
    destination_ids: list[str] = Field(default_factory=list)
    resource_type: ResourceType | None = None
    top_k: int = 5


class SearchTravelKnowledgeOutput(ContractModel):
    evidence: list[Evidence] = Field(default_factory=list)


# --- get_place_facts --------------------------------------------------------


class GetPlaceFactsInput(ContractModel):
    resource_ids: list[str]
    start_date: date
    end_date: date


class GetPlaceFactsOutput(ContractModel):
    facts: list[ResourceCandidate] = Field(default_factory=list)


# --- get_place_availability -------------------------------------------------


class GetPlaceAvailabilityInput(ContractModel):
    resource_id: str
    date: date
    requested_time_window: TimeWindow | None = None


class GetPlaceAvailabilityOutput(ContractModel):
    status: AvailabilityStatus
    time_windows: list[TimeWindow] = Field(default_factory=list)
    reservation_required: bool = False
    reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


# --- get_route --------------------------------------------------------------


class GetRouteInput(ContractModel):
    origin: str
    destination: str
    departure_time: Clock | None = None
    mode: TravelMode | None = None


class GetRouteOutput(ContractModel):
    duration_minutes: int
    distance_km: float | None = None
    estimated_cost: float | None = None
    source: TravelLegSource
    is_estimated: bool = True
    mode: TravelMode | None = None


# --- get_weather ------------------------------------------------------------


class GetWeatherInput(ContractModel):
    destination_id: str
    date: date


class TemperatureRange(ContractModel):
    min_celsius: float
    max_celsius: float


class GetWeatherOutput(ContractModel):
    condition: str
    temperature_range: TemperatureRange | None = None
    precipitation_probability: float | None = None
    source: SourceType
    is_forecast: bool = True
    collected_at: datetime | None = None

