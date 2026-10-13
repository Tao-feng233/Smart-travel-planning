"""Regression tests use explicit transports or service fixtures, never live APIs."""

import httpx
import pytest


@pytest.fixture
def web_candidates(monkeypatch):
    """Isolate discovery/ranking tests from the separately tested search agent."""
    from app.travel import web_research

    def install(rows):
        observations = []

        async def fixture(requirements, task, model, tool, progress, **kwargs):
            observations.append(kwargs)
            return {
                "places": [{"name": p["name"], "description": "测试资料", "evidence": []} for p in rows],
                "guides": [], "summary": "测试资料", "search_calls": 1,
            }

        monkeypatch.setattr(web_research, "research", fixture)
        return observations

    return install


@pytest.fixture(autouse=True)
def isolate_plan_web_research(request, monkeypatch):
    """Schedule unit tests isolate acquisition; marked integration tests run it."""
    if request.node.get_closest_marker("web_search_integration"):
        return
    from app.planning import plan_inputs

    async def fixture_guides(ctx):
        result = await ctx.services.tool("search_travel_web", {
            "query": " ".join(x["name"] for x in ctx.spots) + " 开放 预约",
            "city": ctx.requirements["city"], "source_type": "official",
        })
        return result.get("items", [])

    monkeypatch.setattr(plan_inputs, "acquire_guides", fixture_guides)


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    attempted = []

    async def blocked(self, request):
        attempted.append(request.url.host)
        raise AssertionError("Unexpected live HTTP in regression test")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    yield
    assert not attempted, "Test attempted live HTTP: " + ", ".join(attempted)
