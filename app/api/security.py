"""Origin, host, asset version and response-header policy."""

import hashlib
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import ROOT, setting
from app.api.page_assets import asset_versions

ORIGIN = setting("APP_PUBLIC_ORIGIN", "http://127.0.0.1:8767").rstrip("/")
ORIGINS = {ORIGIN} | (
    {"http://localhost:8767"} if ORIGIN == "http://127.0.0.1:8767" else set()
)
HOSTS = {urlsplit(o).netloc for o in ORIGINS}
PROJECT_ID = hashlib.sha256(str(ROOT.resolve()).casefold().encode()).hexdigest()[:16]
ASSET_VERSIONS = asset_versions(ROOT / "frontend")


def _host_allowed(netloc: str) -> bool:
    """Allow configured public origins and any loopback host/port."""
    if netloc in HOSTS:
        return True
    host, _, _ = netloc.partition(":")
    return host in ("127.0.0.1", "localhost", "::1")


async def security(request: Request, call_next):
    if not _host_allowed(request.url.netloc):
        return JSONResponse({"detail": "不允许的访问域名"}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith(
        "/api/"
    ):
        if request.headers.get("origin") not in ORIGINS:
            return JSONResponse({"detail": "请求来源校验失败"}, status_code=403)
        if "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"detail": "请求必须使用JSON"}, status_code=415)
        try:
            if int(request.headers.get("content-length", "0")) > 65536:
                return JSONResponse(
                    {"detail": "提交内容过大，请缩短后重试"}, status_code=413
                )
        except ValueError:
            return JSONResponse({"detail": "请求长度无效"}, status_code=400)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https: http://store.is.autonavi.com; connect-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path == "/" or request.url.path.startswith(("/api/", "/assets/")):
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.endswith("/map-image") and response.status_code == 200:
            response.headers["Cache-Control"] = "private, max-age=300"
            response.headers["Vary"] = "Cookie"
    return response


async def validation_error(request, exc):
    return JSONResponse(
        {"detail": "填写内容不符合要求，请检查长度、日期、密码或数字范围。"},
        status_code=422,
    )
