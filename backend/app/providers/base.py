"""Private Provider protocol; shared request/response types come from C's Schema."""

from __future__ import annotations

from typing import Protocol

from app.schemas import (
    GetIntercityOptionsRequest,
    GetIntercityOptionsResponse,
    GetPreparationRulesRequest,
    GetPreparationRulesResponse,
    GetResourceAvailabilityRequest,
    GetResourceAvailabilityResponse,
    GetResourceFactsRequest,
    GetResourceFactsResponse,
    GetRouteRequest,
    GetRouteResponse,
    GetWeatherRequest,
    GetWeatherResponse,
    SearchPlanningReadyDestinationsRequest,
    SearchPlanningReadyDestinationsResponse,
    SearchResourcesRequest,
    SearchResourcesResponse,
    SearchTravelKnowledgeRequest,
    SearchTravelKnowledgeResponse,
)


class MCPProvider(Protocol):
    is_mock_only: bool

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsRequest
    ) -> SearchPlanningReadyDestinationsResponse: ...

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeRequest
    ) -> SearchTravelKnowledgeResponse: ...

    def search_resources(
        self, request: SearchResourcesRequest
    ) -> SearchResourcesResponse: ...

    def get_resource_facts(
        self, request: GetResourceFactsRequest
    ) -> GetResourceFactsResponse: ...

    def get_resource_availability(
        self, request: GetResourceAvailabilityRequest
    ) -> GetResourceAvailabilityResponse: ...

    def get_intercity_options(
        self, request: GetIntercityOptionsRequest
    ) -> GetIntercityOptionsResponse: ...

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse: ...

    def get_weather(self, request: GetWeatherRequest) -> GetWeatherResponse: ...

    def get_preparation_rules(
        self, request: GetPreparationRulesRequest
    ) -> GetPreparationRulesResponse: ...


