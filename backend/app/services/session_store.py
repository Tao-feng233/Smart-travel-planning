"""会话状态存储。

P0 按进度报告确定的技术选型：**内存状态 + JSON 快照**，通过 `SessionRepository`
协议抽象；A 线的 MySQL 落库（P1）只需新增一个实现，不改动 LangGraph 节点与 API。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol

from app.graph.stages import PlanStage
from app.schemas import PlanState


class SessionNotFoundError(KeyError):
    """请求的会话不存在。"""


class SessionRepository(Protocol):
    def create(self, session_id: str) -> PlanState: ...

    def get(self, session_id: str) -> PlanState: ...

    def save(self, state: PlanState) -> None: ...

    def exists(self, session_id: str) -> bool: ...


class InMemorySessionRepository:
    """内存实现，可选把每次变更写成 JSON 快照，便于复查与断点续跑。"""

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._states: dict[str, PlanState] = {}
        self._lock = threading.Lock()
        self._snapshot_dir = snapshot_dir
        if self._snapshot_dir is not None:
            self._snapshot_dir.mkdir(parents=True, exist_ok=True)
            self._load_snapshots()

    def create(self, session_id: str) -> PlanState:
        state = PlanState(session_id=session_id, stage=PlanStage.CREATED.value)
        self.save(state)
        return state

    def get(self, session_id: str) -> PlanState:
        with self._lock:
            state = self._states.get(session_id)
        if state is None:
            raise SessionNotFoundError(session_id)
        return state.model_copy(deep=True)

    def save(self, state: PlanState) -> None:
        with self._lock:
            self._states[state.session_id] = state.model_copy(deep=True)
        self._write_snapshot(state)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._states

    # --- 快照 ---------------------------------------------------------------

    def _load_snapshots(self) -> None:
        assert self._snapshot_dir is not None
        for path in sorted(self._snapshot_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                state = PlanState.model_validate(payload)
            except Exception:
                # 快照损坏不应阻断服务启动，跳过并保留文件供人工检查
                continue
            self._states[state.session_id] = state

    def _write_snapshot(self, state: PlanState) -> None:
        if self._snapshot_dir is None:
            return
        path = self._snapshot_dir / f"{state.session_id}.json"
        payload = json.dumps(
            state.model_dump(mode="json"), ensure_ascii=False, indent=2
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
