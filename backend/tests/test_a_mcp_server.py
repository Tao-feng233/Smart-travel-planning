"""A-line MCP Server smoke tests using the official in-memory client."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

pytest.importorskip(
    "mcp",
    reason="MCP SDK未安装；运行 pip install -r backend/requirements.txt 后启用本测试",
)

from mcp import Client

from app.mcp_server.server import create_mcp_server
from app.schemas import Money, TravelerComposition, TripProfile


def _profile() -> TripProfile:
    return TripProfile(
        session_id="sess_mcp",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 4),
        duration_days=3,
        traveler_count=2,
        traveler_composition=TravelerComposition(adults=2),
        budget=Money(amount=5000),
        budget_flexibility="NEGOTIABLE",
        pace="BALANCED",
        interests=["FOOD", "CULTURE"],
        destination_mode="UNKNOWN",
    )


def test_mcp_server_lists_and_calls_nine_typed_tools() -> None:
    async def run() -> None:
        server = create_mcp_server()
        async with Client(server) as client:
            listing = await client.list_tools()
            assert {tool.name for tool in listing.tools} == {
                "search_planning_ready_destinations",
                "search_travel_knowledge",
                "search_resources",
                "get_resource_facts",
                "get_resource_availability",
                "get_intercity_options",
                "get_route",
                "get_weather",
                "get_preparation_rules",
            }
            result = await client.call_tool(
                "search_planning_ready_destinations",
                {
                    "request": {
                        "trip_profile": _profile().model_dump(mode="json"),
                        "top_k": 3,
                    }
                },
            )
            assert result.is_error is False
            assert result.structured_content

    asyncio.run(run())

