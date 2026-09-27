"""REST 路由（v0.4 契约，统一响应信封）。

已实现 `CONTRACTS.md` §13.1 的全部会话接口：

```text
POST /api/sessions                    创建会话
POST /api/sessions/{id}/messages      输入自然语言并推进 LangGraph
GET  /api/sessions/{id}               获取当前 PlanState
```

攻略类接口（`/api/guides/...`）属于 C7，尚未实现。

响应统一为 `{ok, data, warnings, error, trace_id}`：
缺失字段、模拟数据、覆盖不足都属于**正常工作流状态或 warning**，不是 HTTP 错误。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import (
    ConfirmGuideData,
    ConfirmGuideRequest,
    CreateSessionData,
    CreateSessionRequest,
    Envelope,
    ErrorDetail,
    GetGuideData,
    GuideChangeData,
    ModifyGuideRequest,
    RunMode,
    SendMessageData,
    SendMessageRequest,
    WarningItem,
)
from app.services.session_service import (
    GuideNotFoundError,
    GuideNotReadyError,
    GuideVersionConflictError,
    ProfileVersionConflictError,
    SessionService,
)
from app.services.session_store import SessionNotFoundError

from .deps import get_session_service

router = APIRouter(prefix="/api", tags=["sessions"])


def _trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:12]}"


def _session_missing(session_id: str, trace_id: str) -> HTTPException:
    """会话不存在：错误码集合里没有更贴切的取值，暂用 `DATA_MISSING`。"""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=Envelope(
            ok=False,
            data=None,
            error=ErrorDetail(
                code="DATA_MISSING",
                message=f"会话不存在：{session_id}",
                details={"session_id": session_id},
            ),
            trace_id=trace_id,
        ).model_dump(),
    )


def _guide_error(exc: Exception, trace_id: str) -> HTTPException:
    """把攻略相关的异常翻成契约要求的错误码 + HTTP 状态。"""

    if isinstance(exc, GuideNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Envelope(
                ok=False,
                error=ErrorDetail(
                    code="DATA_MISSING",
                    message="攻略不存在。",
                    details={"guide_id": str(exc)},
                ),
                trace_id=trace_id,
            ).model_dump(),
        )
    if isinstance(exc, GuideVersionConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=Envelope(
                ok=False,
                error=ErrorDetail(
                    code="VERSION_CONFLICT",
                    message="攻略版本已过期，请刷新后再修改。",
                    details={
                        "expected_guide_version": str(exc.expected),
                        "current_guide_version": str(exc.actual),
                    },
                ),
                trace_id=trace_id,
            ).model_dump(),
        )
    missing = getattr(exc, "missing", []) or []
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=Envelope(
            ok=False,
            error=ErrorDetail(
                code="DATA_MISSING",
                message=str(exc) or "组装攻略的素材不足。",
                details={item: item for item in missing},
            ),
            trace_id=trace_id,
        ).model_dump(),
    )


def _guide_warnings(guide) -> list[WarningItem]:
    """攻略里登记了 mock 数据时必须显式告知（§14 不变量 5）。"""

    mock_items = list(getattr(guide.sources_and_freshness, "mock_items", []) or [])
    if not mock_items:
        return []
    return [
        WarningItem(
            code="MOCK_DATA_IN_DEMO",
            message="当前数据源包含模拟数据（MOCK_ONLY），仅用于流程验证。",
            details={"count": str(len(mock_items))},
        )
    ]


@router.post(
    "/sessions",
    response_model=Envelope,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    state = service.create_session(run_mode=payload.run_mode or RunMode.DEMO)
    return Envelope(
        ok=True,
        data=CreateSessionData(session_id=state.session_id, state=state).model_dump(
            mode="json"
        ),
        trace_id=_trace_id(),
    )


@router.post("/sessions/{session_id}/messages", response_model=Envelope)
def send_message(
    session_id: str,
    payload: SendMessageRequest,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    trace_id = _trace_id()
    try:
        state, reply, warnings = service.send_message(
            session_id,
            payload.text,
            expected_profile_version=payload.expected_profile_version,
        )
    except SessionNotFoundError:
        raise _session_missing(session_id, trace_id) from None
    except ProfileVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=Envelope(
                ok=False,
                error=ErrorDetail(
                    code="VERSION_CONFLICT",
                    message="画像版本已过期，请刷新后再修改。",
                    details={
                        "expected_profile_version": str(exc.expected),
                        "current_profile_version": str(exc.actual),
                    },
                ),
                trace_id=trace_id,
            ).model_dump(),
        ) from None
    return Envelope(
        ok=True,
        data=reply.model_dump(mode="json"),
        warnings=warnings,
        trace_id=trace_id,
    )


@router.get("/guides/{guide_id}", response_model=Envelope)
def get_guide(
    guide_id: str,
    version: int | None = None,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    """`CONTRACTS.md` §13.2：取攻略（可指定版本）。"""

    trace_id = _trace_id()
    try:
        guide = service.get_guide(guide_id, version)
    except GuideNotFoundError as exc:
        raise _guide_error(exc, trace_id) from None
    return Envelope(
        ok=True,
        data=GetGuideData(travel_guide=guide).model_dump(mode="json"),
        warnings=_guide_warnings(guide),
        trace_id=trace_id,
    )


@router.post("/guides/{guide_id}/confirm", response_model=Envelope)
def confirm_guide(
    guide_id: str,
    payload: ConfirmGuideRequest,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    """确认攻略：锁定指定节点，生成新的攻略版本。"""

    trace_id = _trace_id()
    try:
        guide = service.confirm_guide(
            guide_id,
            expected_guide_version=payload.expected_guide_version,
            lock_node_ids=payload.lock_node_ids,
            idempotency_key=payload.idempotency_key,
        )
    except (GuideNotFoundError, GuideVersionConflictError, GuideNotReadyError) as exc:
        raise _guide_error(exc, trace_id) from None
    return Envelope(
        ok=True,
        data=ConfirmGuideData(travel_guide=guide).model_dump(mode="json"),
        warnings=_guide_warnings(guide),
        trace_id=trace_id,
    )


def _guide_change(guide_id: str, action, service: SessionService) -> Envelope:
    trace_id = _trace_id()
    try:
        guide, lineage, conflicts, notes = service.modify_guide(guide_id, action)
    except (GuideNotFoundError, GuideVersionConflictError, GuideNotReadyError) as exc:
        raise _guide_error(exc, trace_id) from None
    if lineage is None:  # 成功路径一定会带谱系；这里只是防御
        raise _guide_error(
            GuideNotReadyError("修改成功但没有生成版本谱系，已中止。"), trace_id
        )
    return Envelope(
        ok=True,
        data=GuideChangeData(
            travel_guide=guide, version_lineage=lineage, conflicts=list(conflicts)
        ).model_dump(mode="json"),
        warnings=[
            *_guide_warnings(guide),
            *[
                WarningItem(code="CHANGE_NOTE", message=note)
                for note in notes
                if note
            ],
        ],
        trace_id=trace_id,
    )


@router.post("/guides/{guide_id}/modify", response_model=Envelope)
def modify_guide(
    guide_id: str,
    payload: ModifyGuideRequest,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    """用户显式修改（`UserAction.action_type = MODIFY_GUIDE`）。"""

    return _guide_change(guide_id, payload.action, service)


@router.post("/guides/{guide_id}/incident", response_model=Envelope)
def report_incident(
    guide_id: str,
    payload: ModifyGuideRequest,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    """突发事件重规划（`UserAction.action_type = REPORT_INCIDENT`）。"""

    return _guide_change(guide_id, payload.action, service)


@router.get("/sessions/{session_id}", response_model=Envelope)
def get_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> Envelope:
    trace_id = _trace_id()
    try:
        state, _reply, warnings = service.get_state(session_id)
    except SessionNotFoundError:
        raise _session_missing(session_id, trace_id) from None
    return Envelope(
        ok=True,
        data=state.model_dump(mode="json"),
        warnings=warnings,
        trace_id=trace_id,
    )
