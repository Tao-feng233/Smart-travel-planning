"""验证与冲突（`CONTRACTS.md` §8）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RepairAction = Literal[
    "REORDER_NODES",
    "MOVE_NODE",
    "REPLACE_RESOURCE",
    "REMOVE_NODE",
    "ADD_REST",
    "CHANGE_TRAVEL_MODE",
    "REQUEST_USER_CHOICE",
    "RELAX_NEGOTIABLE_CONSTRAINT",
]

ConflictType = Literal[
    "TIME_WINDOW",
    "OPENING_HOURS",
    "BUDGET_EXCEEDED",
    "DAILY_INTENSITY",
    "DISTANCE_EXCESSIVE",
    "RESERVATION_REQUIRED",
    "WEATHER_UNSUITABLE",
    "DAYS_INSUFFICIENT",
    "CONSTRAINT_VIOLATION",
    "DATA_EXPIRED",
    "DATA_UNKNOWN",
]


class RepairOption(BaseModel):
    repair_option_id: str
    action: RepairAction
    description: str
    affected_node_ids: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = False


class Conflict(BaseModel):
    conflict_id: str
    type: ConflictType
    severity: Literal["WARNING", "ERROR"]
    scope: str
    message: str
    affected_node_ids: list[str] = Field(default_factory=list)
    repair_options: list[RepairOption] = Field(default_factory=list)
    #: §8.2 示例给出 `OPEN`，但未定义完整取值集合，暂用字符串接住
    status: str = "OPEN"
