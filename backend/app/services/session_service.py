"""会话服务：把存储、LangGraph 工作流和回复组装串起来。

API 层只调用本服务，不直接接触图或存储实现。
"""

from __future__ import annotations

import uuid
from typing import Callable, Mapping

from app.graph.workflow import run_turn
from app.schemas import AssistantReply, PlanState

from .reply_builder import build_name_lookup, build_reply
from .session_store import SessionRepository


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        graph,
        *,
        known_destinations: Mapping[str, str] | None = None,
        data_is_mock: bool = True,
    ) -> None:
        self._repository = repository
        self._graph = graph
        self._known_destinations = dict(known_destinations or {})
        self._data_is_mock = data_is_mock
        self._name_lookup: Callable[[str], str | None] = build_name_lookup(
            self._known_destinations
        )

    def create_session(self, session_id: str | None = None) -> PlanState:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        return self._repository.create(session_id)

    def send_message(self, session_id: str, text: str) -> tuple[PlanState, AssistantReply]:
        state = self._repository.get(session_id)
        new_state, _context = run_turn(self._graph, state, text)
        self._repository.save(new_state)
        return new_state, self._reply(new_state)

    def get_state(self, session_id: str) -> tuple[PlanState, AssistantReply]:
        state = self._repository.get(session_id)
        return state, self._reply(state)

    def _reply(self, state: PlanState) -> AssistantReply:
        return build_reply(
            state,
            name_lookup=self._name_lookup,
            data_is_mock=self._data_is_mock,
        )
