"""Authenticated task status, streaming progress and cancellation."""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api import auth
from app.application import jobs
from app.api.dependencies import owned
from app.application.workspaces import present
from app.persistence import storage

router = APIRouter()


@router.get("/api/jobs/{jid}")
def job(jid, user=Depends(auth.current_user)):
    j = storage.job(jid, user["id"])
    if not j:
        raise HTTPException(404, "未找到这个任务")
    result = {
        k: j[k]
        for k in (
            "id",
            "workspace_id",
            "status",
            "progress",
            "error",
            "created",
            "updated",
            "action",
            "ui",
        )
    }
    if j["status"] != "running":
        result["workspace"] = present(owned(j["workspace_id"], user))
    return result


@router.get("/api/jobs/{jid}/events")
async def events(jid, request: Request, user=Depends(auth.current_user)):
    if not storage.job(jid, user["id"]):
        raise HTTPException(404, "未找到这个任务")

    async def stream():
        sent = ""
        last_ui = ""
        heartbeat = time.monotonic()

        def event(kind, data):
            return (
                "event: "
                + kind
                + "\ndata: "
                + json.dumps(data, ensure_ascii=False)
                + "\n\n"
            )

        while not await request.is_disconnected():
            j = storage.job(jid, user["id"])
            if not j:
                return
            ui = j.get("ui") or {}
            value = ui.get("reply_text", "")
            if value != sent:
                if value.startswith(sent):
                    yield event("delta", {"text": value[len(sent) :]})
                else:
                    yield event("replace", {"text": value})
                sent = value
            signature = json.dumps(
                {k: v for k, v in ui.items() if k != "reply_text"}, ensure_ascii=False
            )
            if signature != last_ui:
                yield event("progress", {"ui": ui, "progress": j["progress"]})
                last_ui = signature
            if j["status"] != "running":
                yield event("done", job(jid, user))
                return
            if time.monotonic() - heartbeat > 10:
                yield ": keepalive\n\n"
                heartbeat = time.monotonic()
            await asyncio.sleep(0.05)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/api/jobs/{jid}/cancel")
async def cancel(jid, user=Depends(auth.current_user)):
    j = storage.job(jid, user["id"])
    if not j:
        raise HTTPException(404, "未找到这个任务")
    if j["status"] == "running":
        jobs.cancel_running(jid)
    return {"ok": True}
