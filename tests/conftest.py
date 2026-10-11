"""Regression tests use explicit transports or service fixtures, never live APIs."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    attempted = []

    async def blocked(self, request):
        attempted.append(request.url.host)
        raise AssertionError("Unexpected live HTTP in regression test")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    yield
    assert not attempted, "Test attempted live HTTP: " + ", ".join(attempted)
