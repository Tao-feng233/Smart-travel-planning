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
    CreateSessionData,
    CreateSessionRequest,
    Envelope,
    ErrorDetail,
    RunMode,
    SendMessageData,
    SendMessageRequest,
)
from app.services.session_service import ProfileVersionConflictError, SessionService
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
