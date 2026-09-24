"""REST 路由。

当前实现 `CONTRACTS.md` §14 中的会话类接口：

```text
POST /api/sessions                    创建会话
POST /api/sessions/{id}/messages      输入自然语言并推进 LangGraph
GET  /api/sessions/{id}               获取当前 PlanState
```

攻略类接口（/api/guides/...）属于 C7，尚未实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionStateResponse,
)
from app.services.session_service import SessionService
from app.services.session_store import SessionNotFoundError

from .deps import get_session_service

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: CreateSessionRequest | None = None,
    service: SessionService = Depends(get_session_service),
) -> CreateSessionResponse:
    state = service.create_session(payload.session_id if payload else None)
    return CreateSessionResponse(
        session_id=state.session_id, stage=state.stage, state=state
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
def send_message(
    session_id: str,
    payload: SendMessageRequest,
    service: SessionService = Depends(get_session_service),
) -> SendMessageResponse:
    try:
        state, reply = service.send_message(session_id, payload.text)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话不存在：{session_id}",
        ) from None
    return SendMessageResponse(
        session_id=session_id,
        stage=state.stage,
        awaiting_user_input=state.awaiting_user_input,
        reply=reply,
        state=state,
    )


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> SessionStateResponse:
    try:
        state, reply = service.get_state(session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话不存在：{session_id}",
        ) from None
    return SessionStateResponse(
        session_id=session_id,
        stage=state.stage,
        awaiting_user_input=state.awaiting_user_input,
        reply=reply,
        state=state,
    )
