"""Workspace CRUD, map/export access and validated action submission."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api import auth
from app.application import jobs
from app.api.dependencies import owned
from app.application.workspaces import present
from app.core.errors import DataError
from app.persistence import storage

router = APIRouter()


@router.get("/api/workspaces/{wid}/map-image")
async def workspace_map(
    wid: str,
    day: str = "",
    focus: str = "",
    zoom: int | None = Query(None, ge=1, le=17),
    lng: float | None = Query(None, ge=-180, le=180),
    lat: float | None = Query(None, ge=-85, le=85),
    base: bool = False,
    user=Depends(auth.current_user),
):
    from app.integrations import maps

    w = owned(wid, user)
    if focus and focus not in w["catalog"]:
        raise HTTPException(404, "未找到这个地点")
    if (lng is None) != (lat is None):
        raise HTTPException(422, "地图中心需要同时提供经度和纬度。")
    try:
        image, mime = await maps.image(
            maps.points(w, day, focus),
            ordered=bool(day) and not focus,
            **({"zoom": zoom} if zoom is not None else {}),
            **({"center": (lng, lat)} if lng is not None else {}),
            **({"overlays": False} if base else {}),
        )
        return Response(
            image, media_type=mime, headers={"Cache-Control": "private, max-age=300"}
        )
    except DataError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/api/workspaces/latest")
def latest(user=Depends(auth.current_user)):
    return present(storage.latest(user["id"]))


@router.get("/api/workspaces")
def listing(
    q: str = Query(default="", max_length=80),
    archived: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(auth.current_user),
):
    return storage.list_workspaces(user["id"], q.strip(), archived, offset, limit)


@router.post("/api/workspaces", status_code=201)
def create(user=Depends(auth.current_user)):
    return present(storage.new_workspace(user["id"]))


@router.get("/api/workspaces/{wid}")
def workspace(wid, user=Depends(auth.current_user)):
    return present(owned(wid, user))


class Metadata(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None
    revision: int = Field(ge=0)


@router.patch("/api/workspaces/{wid}")
def edit(wid, body: Metadata, user=Depends(auth.current_user)):
    w = owned(wid, user)
    if storage.active_job(wid):
        raise HTTPException(409, "这次旅行还有任务在执行，请完成或停止后再修改")
    if w["revision"] != body.revision:
        raise HTTPException(409, "旅行已更新，请刷新后重试")
    title = body.title.strip() if body.title is not None else None
    if title is not None and not title:
        raise HTTPException(400, "旅行名称不能为空")
    return present(storage.metadata(w, title, body.archived))


@router.delete("/api/workspaces/{wid}")
def delete(wid, user=Depends(auth.current_user)):
    owned(wid, user)
    if storage.active_job(wid):
        raise HTTPException(409, "请先停止这次旅行的任务，再删除")
    storage.delete_workspace(wid, user["id"])
    return {"ok": True}


@router.get("/api/workspaces/{wid}/stations")
async def stations(
    wid: str,
    kind: str = Query("train", pattern="^(train|flight)$"),
    city: str = Query("", max_length=40),
    user=Depends(auth.current_user),
):
    """到达站/返程站下拉的选项来源：按城市取火车站或机场清单。

    缺省用工作区的目的地城市；同时也允许显式传 city（返程站通常是出发城市）。
    查询失败或城市为空时返回空列表，前端退化为可手动输入，不阻断表单。
    """
    from app.travel import stations as station_lookup

    w = owned(wid, user)
    target = (city or "").strip() or str(
        (w.get("requirements") or {}).get("city") or ""
    ).strip()
    rows = await station_lookup.list_stations(target, kind)
    return {"city": target, "kind": kind, "items": rows}


class Action(BaseModel):
    revision: int = Field(ge=0)
    action: str = Field(max_length=40)
    text: str = Field(default="", max_length=3000)
    args: dict = Field(default_factory=dict)
    request_id: uuid.UUID


@router.post("/api/workspaces/{wid}/actions", status_code=202)
async def action(wid: str, body: Action, user=Depends(auth.current_user)):
    w = owned(wid, user)
    if w["archived"]:
        raise HTTPException(409, "这次旅行已归档，请恢复后再继续规划")
    if body.action not in {
        "chat",
        "request_auto_selection",
        "approve_auto_selection",
        "continue_auto_selection",
        "cancel_auto_selection",
        "approve_plan_warning",
        "cancel_plan_warning",
        "requirements",
        "discover_destinations",
        "choose_destination",
        "search_spots",
        "spots_page",
        "dismiss_spot",
        "complete_spots",
        "complete_hotel",
        "skip_hotel",
        "transport_arrangement",
        "search_hotels",
        "search_foods",
        "meal_choice",
        "complete_food",
        "visit_schedule",
        "analyze_visits",
        "adjust_timeline",
        "refresh_routes",
        "review_timeline",
        "optimize_plan",
        "select",
        "select_room",
        "hotel_detail",
        "place_detail",
        "weather",
        "train",
        "flight",
        "ticket",
        "plan",
        "undo",
    }:
        raise HTTPException(400, "不支持的操作")
    if body.action == "chat" and not body.text.strip():
        raise HTTPException(400, "请先输入旅行想法")
    jid = uuid.uuid4().hex
    with storage.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        previous = c.execute(
            "SELECT id,workspace_id FROM jobs WHERE owner_id=? AND request_id=?",
            (user["id"], str(body.request_id)),
        ).fetchone()
        if previous:
            if previous[1] != wid:
                raise HTTPException(409, "请求编号已用于其他旅行")
            return {"job_id": previous[0]}
        if c.execute(
            "SELECT 1 FROM jobs WHERE workspace_id=? AND status='running'", (wid,)
        ).fetchone():
            raise HTTPException(409, "这次旅行正在处理，请等待或停止当前任务")
        if (
            c.execute(
                "SELECT COUNT(*) FROM jobs WHERE owner_id=? AND status='running'",
                (user["id"],),
            ).fetchone()[0]
            >= 2
        ):
            raise HTTPException(429, "最多同时处理两次旅行，请稍后再试")
        if (
            c.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
            >= 4
        ):
            raise HTTPException(503, "服务当前繁忙，请稍后再试")
        if w["revision"] != body.revision:
            raise HTTPException(409, "旅行已更新，请刷新后重试")
        if (
            c.execute(
                "SELECT COUNT(*) FROM jobs WHERE owner_id=? AND created>?",
                (user["id"], storage.now()[:10]),
            ).fetchone()[0]
            >= 500
        ):
            raise HTTPException(429, "今日处理次数已达500次上限，请明天再试")
        c.execute(
            "INSERT INTO jobs(id,owner_id,workspace_id,request_id,status,progress,error,created,updated,action) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                jid,
                user["id"],
                wid,
                str(body.request_id),
                "running",
                "正在准备任务",
                None,
                storage.now(),
                storage.now(),
                body.action,
            ),
        )
    jobs.start(wid, body, jid, user["id"])
    return {"job_id": jid}


@router.get("/api/workspaces/{wid}/export")
def export(wid, user=Depends(auth.current_user)):
    from app.application.report import markdown

    w = owned(wid, user)
    if not w.get("plan"):
        raise HTTPException(400, "请先生成计划书")
    if w["plan"].get("stale"):
        raise HTTPException(409, "当前选择已变化，请重新生成计划书后再导出")
    return Response(
        markdown(w),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="travel-plan.md"'},
    )
