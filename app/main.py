"""Compose HTTP routes and own external-resource startup/shutdown."""

import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.api import auth
from app.api import accounts, jobs, system, workspaces
from app.api.security import security, validation_error
from app.application import jobs as job_runner
from app.core.config import ROOT
from app.core.data_settings import mcp_environment
from app.integrations import maps, request_cache, tools


@asynccontextmanager
async def lifespan(app):
    from app.core import logging as app_logging

    app_logging.configure()
    job_runner.initialize()
    async with AsyncExitStack() as stack:
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "app/integrations/mcp_server.py")],
            cwd=str(ROOT),
            env=mcp_environment(),
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools.SESSION = session
        app.state.tool_names = [
            tool.name for tool in (await session.list_tools()).tools
        ]
        try:
            yield
        finally:
            await job_runner.shutdown()
            tools.SESSION = None
            await maps.close()
            await request_cache.close()


app = FastAPI(
    title="识途", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
)
for router in (
    auth.router,
    system.router,
    workspaces.router,
    jobs.router,
    accounts.router,
):
    app.include_router(router)
app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")


@app.middleware("http")
async def trace(request, call_next):
    """Attach one id to a whole request: logs, and the response header a user can quote."""
    from app.core import logging as app_logging

    value = request.headers.get(app_logging.TRACE_HEADER) or app_logging.new_trace()
    token = app_logging.TRACE_ID.set(value)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Still inside the binding: the record must carry the id of the request that failed.
        app_logging.emit_access(
            request.url.path, request.method, 500, started, {"outcome": "unhandled"}
        )
        raise
    else:
        # Also inside the binding -- resetting first would log trace_id "-".
        response.headers[app_logging.TRACE_HEADER] = value
        app_logging.emit_access(
            request.url.path, request.method, response.status_code, started
        )
    finally:
        app_logging.TRACE_ID.reset(token)
    return response


# Registered after `trace`, so trace is the outermost layer and the id is already
# bound when the security middleware rejects a request.
app.middleware("http")(security)
app.exception_handler(RequestValidationError)(validation_error)
