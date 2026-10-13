"""Application shell, readiness, data coverage and usage endpoints."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.api import auth
from app.api.security import ASSET_VERSIONS, PROJECT_ID
from app.core.config import ROOT, configured
from app.persistence import storage

router = APIRouter()


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


@router.get("/api/status")
def status(request: Request, user=Depends(auth.current_user)):
    return {
        "configured": configured(),
        "tools": getattr(request.app.state, "tool_names", []),
        "data_source": "tavily",
        "rag_enabled_in_app": False,
        "knowledge_cities": [],
        "knowledge_records": None,
        "knowledge_scope": "本地RAG工具独立保留，当前应用使用联网资料，不以本地资料限制城市覆盖。",
    }


@router.get("/api/usage")
def usage(days: int = Query(default=0, ge=0, le=365), user=Depends(auth.current_user)):
    """Aggregate model usage by call label, for cost tuning.

    llm_calls holds counts and latencies only -- no prompts, replies or ids -- so this
    is safe to expose to any signed-in account.
    """
    return storage.usage_summary(days)
