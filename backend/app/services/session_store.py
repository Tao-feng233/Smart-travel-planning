"""会话状态存储（v0.4 契约）。

P0 按进度报告确定的技术选型：**内存状态 + JSON 快照**，通过 `SessionRepository`
协议抽象；A 线的 MySQL 落库（P1）只需新增一个实现，不改动 LangGraph 节点与 API。

`PlanState`（`CONTRACTS.md` §10.2）只保存契约规定的引用，因此会话还需要持有三样
**不属于 `PlanState`** 的数据，统一放在 `SessionExtras` 里一起持久化：

```text
draft                不完整画像（§2.4）
profile              正式画像（§2.3），PlanState 只留 trip_profile_version
run_mode             DEMO / VERIFIED（影响 UNKNOWN 资源能否进规划，§14 不变量 3）
excluded_resources   被前置过滤排除的资源与原因（不得静默丢弃）
```
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.graph.stages import PlanStage
from app.schemas import PlanState, RunMode, TripProfile, TripProfileDraft


class SessionNotFoundError(KeyError):
    """请求的会话不存在。"""


class ExcludedResourceRecord(BaseModel):
    """被前置过滤排除的资源（可复查，不是静默丢弃）。"""

    resource_id: str
    status: str
    reason: str
    unavailable_dates: list[date] = Field(default_factory=list)


class SessionExtras(BaseModel):
    """不属于 `PlanState` 的会话数据。"""

    draft: TripProfileDraft | None = None
    profile: TripProfile | None = None
    run_mode: RunMode = RunMode.DEMO
    excluded_resources: list[ExcludedResourceRecord] = Field(default_factory=list)


class SessionRepository(Protocol):
    def create(self, session_id: str, run_mode: RunMode = RunMode.DEMO) -> PlanState: ...

    def get(self, session_id: str) -> PlanState: ...

    def save(self, state: PlanState) -> None: ...

    def exists(self, session_id: str) -> bool: ...

    def get_extras(self, session_id: str) -> SessionExtras: ...

    def save_extras(self, session_id: str, extras: SessionExtras) -> None: ...


class InMemorySessionRepository:
    """内存实现，可选把每次变更写成 JSON 快照，便于复查与断点续跑。"""

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._states: dict[str, PlanState] = {}
        self._extras: dict[str, SessionExtras] = {}
        self._lock = threading.Lock()
        self._snapshot_dir = snapshot_dir
        if self._snapshot_dir is not None:
            self._snapshot_dir.mkdir(parents=True, exist_ok=True)
            self._load_snapshots()

    def create(self, session_id: str, run_mode: RunMode = RunMode.DEMO) -> PlanState:
        state = PlanState(session_id=session_id, stage=PlanStage.CREATED.value)
        self.save(state)
        self.save_extras(session_id, SessionExtras(run_mode=run_mode))
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

    def get_extras(self, session_id: str) -> SessionExtras:
        with self._lock:
            extras = self._extras.get(session_id)
        return extras.model_copy(deep=True) if extras is not None else SessionExtras()

    def save_extras(self, session_id: str, extras: SessionExtras) -> None:
        with self._lock:
            self._extras[session_id] = extras.model_copy(deep=True)
            state = self._states.get(session_id)
        if state is not None:
            self._write_snapshot(state, extras)

    # --- 快照 ---------------------------------------------------------------

    def _load_snapshots(self) -> None:
        assert self._snapshot_dir is not None
        for path in sorted(self._snapshot_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if "state" not in payload:
                    # 旧版本（v0.3）快照的对象结构已经不同，跳过即可
                    continue
                state = PlanState.model_validate(payload["state"])
                extras = SessionExtras.model_validate(payload.get("extras") or {})
            except Exception:
                # 快照损坏不应阻断服务启动，跳过并保留文件供人工检查
                continue
            self._states[state.session_id] = state
            self._extras[state.session_id] = extras

    def _write_snapshot(
        self, state: PlanState, extras: SessionExtras | None = None
    ) -> None:
        if self._snapshot_dir is None:
            return
        if extras is None:
            extras = self._extras.get(state.session_id) or SessionExtras()
        path = self._snapshot_dir / f"{state.session_id}.json"
        payload = json.dumps(
            {
                "state": state.model_dump(mode="json"),
                "extras": extras.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
