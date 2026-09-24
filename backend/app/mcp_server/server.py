"""Strongly typed MCP v2 server exposing the nine v0.4 travel tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from mcp.server import MCPServer

from app.providers import MCPProvider, build_mcp_provider
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


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    called_at: datetime
    result_count: int


class TravelMCPService:
    """Thin logging facade; no third-party payload leaks above the Provider."""

    def __init__(self, provider: MCPProvider) -> None:
        self.provider = provider
        self.call_log: list[ToolCallRecord] = []

    def record(self, tool_name: str, result_count: int) -> None:
        self.call_log.append(
            ToolCallRecord(
                tool_name=tool_name,
                called_at=datetime.now(UTC),
                result_count=result_count,
            )
        )


def create_mcp_server(provider: MCPProvider | None = None) -> MCPServer:
    service = TravelMCPService(provider or build_mcp_provider())
    server = MCPServer("travel-planner-data")

    @server.tool()
    def search_planning_ready_destinations(
        request: SearchPlanningReadyDestinationsRequest,
    ) -> SearchPlanningReadyDestinationsResponse:
        result = service.provider.search_planning_ready_destinations(request)
        service.record("search_planning_ready_destinations", len(result.recommendations))
        return result

    @server.tool()
    def search_travel_knowledge(
        request: SearchTravelKnowledgeRequest,
    ) -> SearchTravelKnowledgeResponse:
        result = service.provider.search_travel_knowledge(request)
        service.record("search_travel_knowledge", len(result.evidence))
        return result

    @server.tool()
    def search_resources(request: SearchResourcesRequest) -> SearchResourcesResponse:
        result = service.provider.search_resources(request)
        service.record("search_resources", len(result.resources))
        return result

    @server.tool()
    def get_resource_facts(
        request: GetResourceFactsRequest,
    ) -> GetResourceFactsResponse:
        result = service.provider.get_resource_facts(request)
        service.record("get_resource_facts", len(result.facts))
        return result

    @server.tool()
    def get_resource_availability(
        request: GetResourceAvailabilityRequest,
    ) -> GetResourceAvailabilityResponse:
        result = service.provider.get_resource_availability(request)
        service.record("get_resource_availability", 1)
        return result

    @server.tool()
    def get_intercity_options(
        request: GetIntercityOptionsRequest,
    ) -> GetIntercityOptionsResponse:
        result = service.provider.get_intercity_options(request)
        service.record("get_intercity_options", len(result.options))
        return result

    @server.tool()
    def get_route(request: GetRouteRequest) -> GetRouteResponse:
        result = service.provider.get_route(request)
        service.record("get_route", len(result.routes))
        return result

    @server.tool()
    def get_weather(request: GetWeatherRequest) -> GetWeatherResponse:
        result = service.provider.get_weather(request)
        service.record("get_weather", len(result.weather_facts))
        return result

    @server.tool()
    def get_preparation_rules(
        request: GetPreparationRulesRequest,
    ) -> GetPreparationRulesResponse:
        result = service.provider.get_preparation_rules(request)
        service.record("get_preparation_rules", len(result.rules))
        return result

    server.travel_service = service  # type: ignore[attr-defined]
    return server


mcp = create_mcp_server()


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8001")),
            json_response=True,
        )
    else:
        mcp.run()


