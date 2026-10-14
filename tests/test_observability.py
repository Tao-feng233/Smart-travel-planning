"""Health, readiness and metrics exposition -- the three endpoints ops actually hits.

Readiness is the interesting one: it must distinguish hard dependencies (the
process genuinely cannot serve) from soft ones it is *designed* to run without.
A probe that returns 503 whenever the vector index is absent would report a
supported degraded mode as an outage.
"""

import re
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app import main
from app.application import jobs as job_runner
from app.persistence import storage

METRIC_NAME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})? (.+)$")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB", tmp_path / "test.db")
    storage.init()

    @asynccontextmanager
    async def lifespan(app):
        job_runner.TASKS.clear()
        yield

    monkeypatch.setattr(main.app.router, "lifespan_context", lifespan)
    # Without a real MCP stdio session the readiness probe is right to fail, so
    # tests that expect "ready" install a stand-in and assert on the contract.
    from app.integrations import tools

    monkeypatch.setattr(tools, "SESSION", object(), raising=False)
    with TestClient(
        main.app,
        base_url="http://127.0.0.1:8767",
        headers={"Origin": "http://127.0.0.1:8767", "Content-Type": "application/json"},
    ) as c:
        yield c


def test_healthz_reports_service(client):
    body = client.get("/api/healthz").json()
    assert body["status"] == "ok" and body["service"] == "shitu"


def test_readyz_ready_when_required_dependencies_hold(client):
    response = client.get("/api/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["sqlite"]["required"] is True
    assert body["checks"]["tools"]["required"] is True
    assert body["checks"]["vector_index"]["required"] is False


def test_readyz_fails_when_tool_session_is_gone(client, monkeypatch):
    from app.integrations import tools

    monkeypatch.setattr(tools, "SESSION", None, raising=False)
    response = client.get("/api/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["tools"]["ok"] is False


def test_readyz_stays_ready_when_only_the_index_is_missing(client, monkeypatch, tmp_path):
    """A missing vector index is a supported degraded mode, not an outage."""
    from app.core import data_settings

    monkeypatch.setattr(data_settings, "index_root", lambda: tmp_path / "no-such-index")
    response = client.get("/api/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["degraded"] == ["vector_index"]
    assert body["checks"]["vector_index"]["ok"] is False


def _split_labels(raw):
    """Split on commas that are not inside a quoted label value."""
    out, buf, quoted, escaped = [], "", False, False
    for ch in raw:
        if escaped:
            buf += ch
            escaped = False
            continue
        if ch == "\\":
            buf += ch
            escaped = True
            continue
        if ch == '"':
            quoted = not quoted
            buf += ch
            continue
        if ch == "," and not quoted:
            out.append(buf)
            buf = ""
            continue
        buf += ch
    out.append(buf)
    return out


def test_trace_id_is_returned_and_propagated(client):
    first = client.get("/api/healthz")
    issued = first.headers.get("x-trace-id")
    assert issued and issued != "-"
    # A caller-supplied id must survive: one id for the whole call chain.
    second = client.get("/api/healthz", headers={"X-Trace-Id": "caller-supplied"})
    assert second.headers["x-trace-id"] == "caller-supplied"


def test_trace_id_is_bound_while_the_access_log_is_written(client, monkeypatch):
    """Regression guard: resetting the context var before logging yields trace_id "-".

    The middleware emits the access record inside the binding; moving the reset
    earlier silently empties every log line and nothing else fails.
    """
    from app.core import logging as app_logging

    seen = {}
    original = app_logging.emit_access

    def spy(path, method, status, started, extra=None):
        seen["trace_id"] = app_logging.trace_id()
        return original(path, method, status, started, extra)

    monkeypatch.setattr(app_logging, "emit_access", spy)
    response = client.get("/api/healthz")
    assert seen.get("trace_id") == response.headers["x-trace-id"]
    assert seen["trace_id"] != "-"


def test_json_formatter_emits_one_object_per_line_with_extras():
    import json
    import logging

    from app.core import logging as app_logging

    record = logging.LogRecord(
        "shitu.access", logging.INFO, __file__, 1, "request", None, None
    )
    record.duration_ms = 12.5
    with app_logging.bound("trace-xyz"):
        text = app_logging.JsonFormatter().format(record)
    payload = json.loads(text)
    assert payload["trace_id"] == "trace-xyz"
    assert payload["duration_ms"] == 12.5
    assert payload["level"] == "INFO"


def test_metrics_is_prometheus_text(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in response.headers["content-type"]
    assert response.text.strip()


def test_metrics_lines_follow_the_text_protocol(client):
    """Every sample needs a declared TYPE, and counters must be named *_total."""
    body = client.get("/api/metrics").text
    declared = {}
    pending = None
    for line in body.splitlines():
        if not line:
            pending = None
            continue
        if line.startswith("# "):
            parts = line[2:].split(" ", 1)
            if parts[0] == "TYPE":
                name, kind = parts[1].rsplit(" ", 1)
                declared[name] = kind
            continue
        match = SAMPLE.match(line)
        assert match, "非法的指标行: " + line
        name = match.group(1)
        assert name in declared, "样本先于 TYPE 声明: " + name
        assert METRIC_NAME.match(name)
        if declared[name] == "counter":
            assert name.endswith("_total"), "计数器名必须以 _total 结尾: " + name
        float(match.group(3))
        if match.group(2):
            for pair in _split_labels(match.group(2)):
                assert re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*="', pair), pair
    for name in ("shitu_up", "shitu_jobs_total", "shitu_llm_calls_total"):
        assert name in declared


def test_metrics_expose_counts_without_identity(client):
    """Aggregates only: no account ids, no request payloads."""
    body = client.get("/api/metrics").text
    assert "shitu_jobs_in_flight" in body
    assert "shitu_llm_calls_total" in body
    lowered = body.lower()
    # "token" is a legitimate metric word (shitu_llm_tokens_total); what must never
    # appear is an identity or a credential.
    for leaked in ("@", "password", "bearer", "cookie", "session="):
        assert leaked not in lowered


def test_security_allows_loopback_on_any_port(client):
    """Container smoke tests map the app to arbitrary host ports; loopback must still work."""
    response = client.get("/api/healthz", headers={"Host": "127.0.0.1:8768"})
    assert response.status_code == 200
    response = client.get("/api/healthz", headers={"Host": "localhost:9999"})
    assert response.status_code == 200


def test_security_rejects_unknown_public_host(client):
    """Configured public origin is still enforced for non-loopback hosts."""
    response = client.get("/api/healthz", headers={"Host": "evil.example.com"})
    assert response.status_code == 400
    assert "不允许的访问域名" in response.text
