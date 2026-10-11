"""Account data export/deletion and user feedback."""

import json
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.api import auth
from app.persistence import storage

router = APIRouter()


class Feedback(BaseModel):
    category: str = Field(default="product", max_length=20)
    content: str = Field(min_length=5, max_length=3000)


@router.post("/api/feedback", status_code=201)
def feedback(body: Feedback, user=Depends(auth.current_user)):
    if body.category not in {"product", "data", "bug", "other"}:
        raise HTTPException(400, "请选择反馈类型")
    content = body.content.strip()
    if len(content) < 5:
        raise HTTPException(400, "请补充至少5个字的反馈")
    with storage.connect() as c:
        if (
            c.execute(
                "SELECT COUNT(*) FROM feedback WHERE owner_id=? AND created>?",
                (user["id"], storage.now()[:10]),
            ).fetchone()[0]
            >= 10
        ):
            raise HTTPException(429, "今天反馈较多，请明天再提交")
        fid = uuid.uuid4().hex
        c.execute(
            "INSERT INTO feedback VALUES(?,?,?,?,?,?)",
            (fid, user["id"], body.category, content, storage.now(), "received"),
        )
    return {"id": fid, "status": "received"}


@router.get("/api/feedback")
def feedback_list(user=Depends(auth.current_user)):
    with storage.connect() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT id,category,content,created,status FROM feedback WHERE owner_id=? ORDER BY created DESC LIMIT 30",
            (user["id"],),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/api/account/export")
def account_export(user=Depends(auth.current_user)):
    with storage.connect() as c:
        ids = [
            r[0]
            for r in c.execute(
                "SELECT id FROM workspaces WHERE owner_id=?", (user["id"],)
            )
        ]
    data = {
        "user": auth.public_user(user),
        "exported_at": storage.now(),
        "workspaces": [storage.get(wid, user["id"]) for wid in ids],
        "feedback": feedback_list(user)["items"],
    }
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="shitu-account-data.json"'
        },
    )


@router.delete("/api/account")
def delete_account(
    body: auth.Confirmation, request: Request, user=Depends(auth.current_user)
):
    auth.throttle(request, user["username"])
    if not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(400, "密码不正确")
    with storage.connect() as c:
        if c.execute(
            "SELECT 1 FROM jobs WHERE owner_id=? AND status='running'", (user["id"],)
        ).fetchone():
            raise HTTPException(409, "请先停止所有旅行任务，再注销账户")
        ids = [
            r[0]
            for r in c.execute(
                "SELECT id FROM workspaces WHERE owner_id=?", (user["id"],)
            )
        ]
        for wid in ids:
            c.execute("DELETE FROM versions WHERE id=?", (wid,))
        c.execute("DELETE FROM workspaces WHERE owner_id=?", (user["id"],))
        c.execute("DELETE FROM users WHERE id=?", (user["id"],))
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE, path="/")
    return response
