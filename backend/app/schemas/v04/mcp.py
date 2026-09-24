"""9 个 MCP 工具的请求/响应模型（`CONTRACTS.md` §12）。

P0 允许工具背后使用 Mock / Snapshot / Live / Hybrid Provider，
但**返回结构必须一致**，因此这里把每个工具的输入输出固定下来。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .candidates import ResourceCandidateUnion
from .models import (
    Evidence,
    FactRecord,
    IntercityOption,
    Money,
    PlanningFact,
    PlanningReadinessEvaluation,
    PreparationRule,
    TimeWindow,
    TripProfile,
)
from .recommendation import DestinationRecommendation

#: 与 `CONTRACTS.md` §1.3 一致的字段级字面量类型。
SourceTypeLiteral = Literal[
    "OFFICIAL", "AUTHORITY", "PLATFORM", "GUIDE", "MANUAL", "DERIVED", "MOCK"
]
TravelModeLiteral = Literal[
    "WALK", "METRO", "BUS", "TAXI", "BIKE", "RAIL", "FLIGHT", "INTERCITY_BUS", "OTHER"
]
DataAssuranceStatusLiteral = Literal["VERIFIED", "DEGRADED", "MOCK", "INSUFFICIENT"]


class DateRange(BaseModel):
    start_date: date
    end_date: date


# --- 12.1 search_planning_ready_destinations --------------------------------


class SearchPlanningReadyDestinationsRequest(BaseModel):
    trip_profile: TripProfile
    top_k: int = 5


class SearchPlanningReadyDestinationsResponse(BaseModel):
    recommendations: list[DestinationRecommendation] = Field(default_factory=list)
    readiness_evaluations: list[PlanningReadinessEvaluation] = Field(
        default_factory=list
    )


# --- 12.2 search_travel_knowledge -------------------------------------------


class SearchTravelKnowledgeRequest(BaseModel):
    query: str
    destination_ids: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    top_k: int = 5


class SearchTravelKnowledgeResponse(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)


# --- 12.3 search_resources --------------------------------------------------


class SearchResourcesRequest(BaseModel):
    resource_type: Literal[
        "VISIT_PLACE", "RESTAURANT", "LODGING", "LODGING_AREA", "INTERCITY_OPTION"
    ]
    destination_id: str
    area_ids: list[str] = Field(default_factory=list)
    date_range: DateRange
    filters: dict[str, str] = Field(default_factory=dict)


class SearchResourcesResponse(BaseModel):
    resources: list[ResourceCandidateUnion] = Field(default_factory=list)


# --- 12.4 get_resource_facts ------------------------------------------------


class GetResourceFactsRequest(BaseModel):
    resource_ids: list[str]
    fact_types: list[str] = Field(default_factory=list)
    date_range: DateRange | None = None


class GetResourceFactsResponse(BaseModel):
    facts: list[FactRecord] = Field(default_factory=list)
    planning_facts: list[PlanningFact] = Field(default_factory=list)


# --- 12.5 get_resource_availability -----------------------------------------


class GetResourceAvailabilityRequest(BaseModel):
    resource_id: str
    date: date
    requested_window: TimeWindow | None = None


class GetResourceAvailabilityResponse(BaseModel):
    status: Literal["AVAILABLE", "CONDITIONAL", "UNAVAILABLE", "UNKNOWN"]
    available_windows: list[TimeWindow] = Field(default_factory=list)
    reservation_required: bool = False
    reason: str | None = None
    planning_fact_ids: list[str] = Field(default_factory=list)


# --- 12.6 get_intercity_options ---------------------------------------------


class GetIntercityOptionsRequest(BaseModel):
    origin_city: str
    destination_id: str
    arrival_or_departure_date: date
    traveler_constraints: list[str] = Field(default_factory=list)


class GetIntercityOptionsResponse(BaseModel):
    options: list[IntercityOption] = Field(default_factory=list)


# --- 12.7 get_route ---------------------------------------------------------


class GetRouteRequest(BaseModel):
    origin: str
    destination: str
    depart_at: datetime | None = None
    allowed_modes: list[TravelModeLiteral] = Field(default_factory=list)


class RouteOption(BaseModel):
    mode: TravelModeLiteral
    duration_minutes: int
    distance_km: float | None = None
    estimated_cost: Money | None = None
    walking_minutes: int | None = None
    transfer_count: int | None = None
    congestion_level: str | None = None
    source: SourceTypeLiteral
    is_estimated: bool = True
    planning_fact_id: str | None = None


class GetRouteResponse(BaseModel):
    routes: list[RouteOption] = Field(default_factory=list)


# --- 12.8 get_weather -------------------------------------------------------


class GetWeatherRequest(BaseModel):
    destination_id: str | None = None
    coordinate: str | None = None
    date_range: DateRange


class WeatherFact(BaseModel):
    date: date
    condition: str
    temperature_min_celsius: float | None = None
    temperature_max_celsius: float | None = None
    precipitation_probability: float | None = None
    source: SourceTypeLiteral
    is_forecast: bool = True
    data_assurance_status: DataAssuranceStatusLiteral
    planning_fact_id: str | None = None


class GetWeatherResponse(BaseModel):
    weather_facts: list[WeatherFact] = Field(default_factory=list)


# --- 12.9 get_preparation_rules ---------------------------------------------


class GetPreparationRulesRequest(BaseModel):
    trip_profile: TripProfile
    activity_tags: list[str] = Field(default_factory=list)
    weather_facts: list[WeatherFact] = Field(default_factory=list)


class GetPreparationRulesResponse(BaseModel):
    rules: list[PreparationRule] = Field(default_factory=list)


MCP_TOOL_MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "search_planning_ready_destinations": (
        SearchPlanningReadyDestinationsRequest,
        SearchPlanningReadyDestinationsResponse,
    ),
    "search_travel_knowledge": (
        SearchTravelKnowledgeRequest,
        SearchTravelKnowledgeResponse,
    ),
    "search_resources": (SearchResourcesRequest, SearchResourcesResponse),
    "get_resource_facts": (GetResourceFactsRequest, GetResourceFactsResponse),
    "get_resource_availability": (
        GetResourceAvailabilityRequest,
        GetResourceAvailabilityResponse,
    ),
    "get_intercity_options": (
        GetIntercityOptionsRequest,
        GetIntercityOptionsResponse,
    ),
    "get_route": (GetRouteRequest, GetRouteResponse),
    "get_weather": (GetWeatherRequest, GetWeatherResponse),
    "get_preparation_rules": (
        GetPreparationRulesRequest,
        GetPreparationRulesResponse,
    ),
}
