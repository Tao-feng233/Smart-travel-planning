"""Application shell, readiness, data coverage and usage endpoints."""

import json
import os
import socket
import sys
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.api import auth
from app.api.security import ASSET_VERSIONS, PROJECT_ID
from app.core.config import ROOT, configured
from app.persistence import storage

router = APIRouter()
STARTED = time.time()


@router.get("/")
def home():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    for name, version in ASSET_VERSIONS.items():
        html = html.replace(f'/assets/{name}"', f'/assets/{name}?v={version}"')
    return Response(html, media_type="text/html")


@router.get("/api/healthz")
def health():
    with storage.connect() as c:
        c.execute("SELECT 1").fetchone()
    return {"status": "ok", "service": "shitu", "project_id": PROJECT_ID}


def _probe_sqlite():
    """Readable + writable: a read-only mount would pass SELECT 1 and still be broken."""
    try:
        with storage.connect() as c:
            c.execute("SELECT 1").fetchone()
        path = str(storage.DB)
        if not os.access(path, os.W_OK) or not os.access(
            os.path.dirname(path) or ".", os.W_OK
        ):
            return False, "数据库文件不可写: " + path
        return True, path
    except Exception as err:  # noqa: BLE001 - probe must never raise
        return False, "数据库不可用: " + type(err).__name__


def _probe_tools():
    """The MCP stdio session is a hard dependency: without it every action fails."""
    from app.integrations import tools

    session = tools.SESSION
    names = None
    try:
        names = session and getattr(session, "_tool_names", None)
    except Exception:  # noqa: BLE001
        names = None
    if session is None:
        return False, "MCP 工具会话未建立"
    return True, ("已连接" + ("（%d 个工具）" % len(names) if names else ""))


def _probe_index():
    """Vector index is a *soft* dependency: absent index degrades to BM25, by design."""
    from app.core.data_settings import index_root, option

    url = option("QDRANT_URL")
    if url:
        parts = urlsplit(url if "://" in url else "http://" + url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or 6333
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True, "server %s:%d 可达" % (host, port)
        except OSError:
            return False, "Qdrant 服务 %s:%d 不可达" % (host, port)
    root = index_root()
    manifest = root / "manifest.json"
    if not manifest.exists():
        # Not a failure: retrieval falls back to BM25 when no index is published.
        return False, "无已发布索引（检索降级为 BM25）: %s" % root
    try:
        json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False, "索引 manifest 不可读: %s" % manifest
    return True, "local %s" % root


# Soft dependencies are reported but never make the process unready: the system is
# designed to run degraded, so a readiness probe that fails on them would only lie.
REQUIRED_CHECKS = ("sqlite", "tools")


@router.get("/api/readyz")
def ready():
    checks = {
        "sqlite": _probe_sqlite(),
        "tools": _probe_tools(),
        "vector_index": _probe_index(),
    }
    body = {
        name: {"ok": ok, "required": name in REQUIRED_CHECKS, "detail": detail}
        for name, (ok, detail) in checks.items()
    }
    degraded = sorted(
        name for name, (ok, _) in checks.items() if not ok and name not in REQUIRED_CHECKS
    )
    ready_ok = all(checks[name][0] for name in REQUIRED_CHECKS)
    payload = {
        "status": "ready" if ready_ok else "not_ready",
        "degraded": degraded,
        "checks": body,
    }
    if not ready_ok:
        return JSONResponse(payload, status_code=503)
    return payload


@router.get("/api/status")
def status(request: Request, user=Depends(auth.current_user)):
    from app.knowledge.retrieval import corpus

    knowledge = corpus()
    return {
        "configured": configured(),
        "tools": getattr(request.app.state, "tool_names", []),
        "knowledge_cities": sorted({p["city"] for p in knowledge["parents"].values()}),
        "knowledge_records": knowledge["records"],
        "knowledge_scope": "已收录的官方特色、历史背景及部分运营快照；出游日适用性需核实",
    }


@router.get("/api/usage")
def usage(days: int = Query(default=0, ge=0, le=365), user=Depends(auth.current_user)):
    """Aggregate model usage by call label, for cost tuning.

    llm_calls holds counts and latencies only -- no prompts, replies or ids -- so this
    is safe to expose to any signed-in account.
    """
    return storage.usage_summary(days)


def _esc(value, for_label=False):
    text = str(value)
    text = text.replace("\\", "\\\\").replace("\n", "\\n")
    return text.replace('"', '\\"') if for_label else text


def _line(name, value, labels=None):
    if labels:
        joined = ",".join('%s="%s"' % (k, _esc(v, True)) for k, v in sorted(labels.items()))
        return "%s{%s} %s" % (name, joined, value)
    return "%s %s" % (name, value)


def _emit(out, name, kind, help_text, rows):
    """rows: list of (value, labels|None). Empty rows still emit TYPE/HELP."""
    out.append("# HELP %s %s" % (name, _esc(help_text)))
    out.append("# TYPE %s %s" % (name, kind))
    for value, labels in rows:
        out.append(_line(name, value, labels))
    out.append("")


def _job_counts():
    with storage.connect() as c:
        return dict(c.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())


def _scalar(sql):
    with storage.connect() as c:
        row = c.execute(sql).fetchone()
    return row[0] if row else 0


@router.get("/api/metrics")
def metrics():
    """Prometheus text exposition of counters the process already keeps.

    Hand-written on purpose: the values exist in-process, and adding
    prometheus_client for a dozen counters buys a dependency, not a capability.
    """
    from app.application import jobs as job_runner
    from app.integrations import request_cache

    pool = request_cache.metrics
    usage = storage.usage_summary(0)
    counts = _job_counts()
    out = []
    _emit(
        out,
        "shitu_build_info",
        "gauge",
        "Build identity of the running process.",
        [(1, {"python": _esc(sys.version.split()[0]), "project_id": PROJECT_ID})],
    )
    _emit(
        out, "shitu_up", "gauge", "1 while the process is serving.", [(1, None)]
    )
    _emit(
        out,
        "shitu_uptime_seconds",
        "gauge",
        "Seconds since this process started.",
        [(round(time.time() - STARTED, 3), None)],
    )
    _emit(
        out,
        "shitu_http_clients",
        "gauge",
        "Cached httpx clients kept per event loop and timeout.",
        [(pool.get("http_clients", 0), None)],
    )
    _emit(
        out,
        "shitu_singleflight_started_total",
        "counter",
        "Coalesced upstream requests created.",
        [(pool.get("started", 0), None)],
    )
    _emit(
        out,
        "shitu_singleflight_joined_total",
        "counter",
        "Requests that joined an already in-flight identical request.",
        [(pool.get("joined", 0), None)],
    )
    _emit(
        out,
        "shitu_jobs_total",
        "counter",
        "Actions by terminal status.",
        [(counts.get(k, 0), {"status": k}) for k in sorted(counts)],
    )
    _emit(
        out,
        "shitu_jobs_in_flight",
        "gauge",
        "Actions currently running in this process.",
        [(len(job_runner.TASKS), None)],
    )
    _emit(
        out,
        "shitu_llm_calls_total",
        "counter",
        "Model calls recorded in llm_calls.",
        [(usage.get("llm_calls", 0), None)],
    )
    _emit(
        out,
        "shitu_llm_calls_failed_total",
        "counter",
        "Model calls recorded as not ok.",
        [(usage.get("failed", 0), None)],
    )
    _emit(
        out,
        "shitu_llm_tokens_total",
        "counter",
        "Tokens billed across all recorded model calls.",
        [(usage.get("total_tokens", 0), None)],
    )
    _emit(
        out,
        "shitu_llm_calls_by_label_total",
        "counter",
        "Model calls per call label.",
        [
            (row["calls"], {"label": row["label"]})
            for row in usage.get("by_label", [])
        ],
    )
    _emit(
        out,
        "shitu_llm_avg_ms_by_label",
        "gauge",
        "Mean model call latency per call label, milliseconds.",
        [
            (row["avg_ms"] or 0, {"label": row["label"]})
            for row in usage.get("by_label", [])
        ],
    )
    _emit(
        out,
        "shitu_workspaces_total",
        "gauge",
        "Workspaces stored.",
        [(_scalar("SELECT COUNT(*) FROM workspaces"), None)],
    )
    return Response("\n".join(out) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")
