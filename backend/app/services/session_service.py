"""会话服务：把存储、LangGraph 工作流和回复组装串起来（v0.4 契约）。

API 层只调用本服务，不直接接触图或存储实现。
"""

from __future__ import annotations

import uuid
from typing import Callable, Mapping

from app.graph.workflow import run_turn
from app.schemas import (
    PlanState,
    RunMode,
    SendMessageData,
    WarningItem,
)

from .reply_builder import build_name_lookup, build_reply, build_warnings
from .session_store import (
    ExcludedResourceRecord,
    SessionExtras,
    SessionRepository,
)


class ProfileVersionConflictError(Exception):
    """调用方持有的 `expected_profile_version` 与当前版本不一致。"""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected_profile_version={expected}，当前={actual}")
        self.expected = expected
        self.actual = actual


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

    def create_session(
        self, session_id: str | None = None, run_mode: RunMode = RunMode.DEMO
    ) -> PlanState:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        return self._repository.create(session_id, run_mode)

    def send_message(
        self,
        session_id: str,
        text: str,
        expected_profile_version: int | None = None,
    ) -> tuple[PlanState, SendMessageData, list[WarningItem]]:
        state = self._repository.get(session_id)
        extras = self._repository.get_extras(session_id)

        current_version = extras.profile.profile_version if extras.profile else None
        if (
            expected_profile_version is not None
            and current_version is not None
            and expected_profile_version != current_version
        ):
            raise ProfileVersionConflictError(expected_profile_version, current_version)

        new_state, context = run_turn(
            self._graph,
            state,
            text,
            draft=extras.draft,
            profile=extras.profile,
            run_mode=extras.run_mode,
        )
        extras.draft = context.draft
        extras.profile = context.profile
        extras.excluded_resources = _excluded_records(context)

        self._repository.save(new_state)
        self._repository.save_extras(session_id, extras)

        reply = build_reply(
            new_state,
            draft=extras.draft,
            profile=extras.profile,
            recommendations=context.recommendations,
            filter_result=context.filter_result,
            name_lookup=self._name_lookup,
            data_is_mock=self._data_is_mock,
        )
        warnings = build_warnings(
            new_state, draft=extras.draft, data_is_mock=self._data_is_mock
        )
        return new_state, reply, warnings

    def get_state(
        self, session_id: str
    ) -> tuple[PlanState, SendMessageData, list[WarningItem]]:
        state = self._repository.get(session_id)
        extras = self._repository.get_extras(session_id)
        reply = build_reply(
            state,
            draft=extras.draft,
            profile=extras.profile,
            name_lookup=self._name_lookup,
            data_is_mock=self._data_is_mock,
        )
        warnings = build_warnings(
            state, draft=extras.draft, data_is_mock=self._data_is_mock
        )
        return state, reply, warnings


def _excluded_records(context) -> list[ExcludedResourceRecord]:
    """把本轮前置过滤排除的资源整理成可持久化的记录。"""

    result = context.filter_result
    if result is None:
        return []
    return [
        ExcludedResourceRecord(
            resource_id=item.resource_id,
            status=item.status,
            reason=item.reason,
            unavailable_dates=result.unavailable_dates.get(item.resource_id, []),
        )
        for item in result.excluded
    ]
