"""状态、版本谱系与用户动作（`CONTRACTS.md` §10、§11）。"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChangeType = Literal[
    "REMOVE_NODE",
    "REPLACE_NODE",
    "ADD_FIXED_NODE",
    "LOWER_INTENSITY",
    "CHANGE_DATE",
    "CHANGE_BUDGET",
    "CHANGE_PACE",
    "CHANGE_LODGING",
]

ScopeHint = Literal["NODE", "DAY", "STAY_SEGMENT", "TRIP_SEGMENT", "WHOLE_GUIDE"]

ActionType = Literal[
    "SELECT_DESTINATION", "CONFIRM_GUIDE", "MODIFY_GUIDE", "REPORT_INCIDENT"
]


class ReplacementRelation(BaseModel):
    old_node_id: str
    new_node_id: str


class VersionLineage(BaseModel):
    change_request_id: str
    parent_plan_version: int | None = None
    new_plan_version: int | None = None
    parent_guide_version: int | None = None
    new_guide_version: int | None = None
    preserved_node_ids: list[str] = Field(default_factory=list)
    changed_node_ids: list[str] = Field(default_factory=list)
    removed_node_ids: list[str] = Field(default_factory=list)
    replacement_relations: list[ReplacementRelation] = Field(default_factory=list)


class PlanState(BaseModel):
    """LangGraph 状态（§10.2）。

    注意：v0.3 曾把 `profile` / `current_plan` / `current_guide` 内嵌在状态里，
    v0.4 改为只保存 ID 与版本号，对象本身由稳定的版本化存储持有。
    """

    session_id: str
    stage: str
    trip_profile_version: int = 0
    destination_candidate_ids: list[str] = Field(default_factory=list)
    resource_candidate_ids: list[str] = Field(default_factory=list)
    current_plan_id: str | None = None
    current_plan_version: int | None = None
    current_guide_id: str | None = None
    current_guide_version: int | None = None
    conflict_ids: list[str] = Field(default_factory=list)
    locked_node_ids: list[str] = Field(default_factory=list)
    completed_node_ids: list[str] = Field(default_factory=list)
    active_incidents: list[str] = Field(default_factory=list)
    data_snapshot_id: str | None = None
    repair_attempts: int = 0
    awaiting_user_input: bool = False


class ActionChangePayload(BaseModel):
    change_type: ChangeType
    scope_hint: ScopeHint
    #: 用 `datetime.date` 而不是裸 `date`：本字段名就叫 date，
    #: 在类命名空间里会遮蔽同名类型，导致注解无法求值。
    date: datetime.date | None = None
    target_node_ids: list[str] = Field(default_factory=list)


class UserAction(BaseModel):
    action_id: str
    #: 重复的 idempotency_key 不得生成重复版本（§11）
    idempotency_key: str | None = None
    action_type: ActionType
    session_id: str
    guide_id: str | None = None
    expected_guide_version: int | None = None
    raw_text: str | None = None
    payload: ActionChangePayload | None = None
