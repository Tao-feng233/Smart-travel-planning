"""REST 契约（`CONTRACTS.md` §13）。

统一响应信封：

```json
{"ok": true, "data": {}, "warnings": [], "error": null, "trace_id": "trace_001"}
```

缺失字段和 Provider 降级属于正常工作流状态或 warning，不作为 HTTP 错误。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import (
    RunMode,
    TravelGuide,
    TripProfile,
)
from .planning import Conflict
from .recommendation import DestinationRecommendation
from .state import PlanState, UserAction, VersionLineage

ErrorCode = Literal[
    "CONTRACT_MISMATCH",
    "VERSION_CONFLICT",
    "OUT_OF_KNOWLEDGE_COVERAGE",
    "DATA_MISSING",
    "NO_FEASIBLE_PLAN",
    "DATA_EXPIRED",
    "VALIDATION_FAILED",
    "PROVIDER_UNAVAILABLE",
]


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, str] = Field(default_factory=dict)


class WarningItem(BaseModel):
    #: 警告不限于错误码集合（例如 DEGRADED_DATA、MOCK_DATA_IN_DEMO）
    code: str
    message: str
    details: dict[str, str] = Field(default_factory=dict)


class Envelope(BaseModel):
    """统一响应信封。`data` 的具体类型由各接口决定。"""

    ok: bool = True
    data: Any = None
    warnings: list[WarningItem] = Field(default_factory=list)
    error: ErrorDetail | None = None
    trace_id: str | None = None


# --- 13.1 会话 --------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    run_mode: RunMode
    timezone: str = "Asia/Shanghai"


class CreateSessionData(BaseModel):
    session_id: str
    state: PlanState


class SendMessageRequest(BaseModel):
    text: str
    expected_profile_version: int | None = None


class SendMessageData(BaseModel):
    stage: str
    assistant_message: str
    trip_profile: TripProfile | None = None
    destination_candidates: list[DestinationRecommendation] = Field(
        default_factory=list
    )
    guide_id: str | None = None
    conflicts: list[Conflict] = Field(default_factory=list)
    degraded_items: list[str] = Field(default_factory=list)


# --- 13.2 攻略 --------------------------------------------------------------


class GetGuideData(BaseModel):
    travel_guide: TravelGuide


class ConfirmGuideRequest(BaseModel):
    expected_guide_version: int
    lock_node_ids: list[str] = Field(default_factory=list)
    idempotency_key: str


class ConfirmGuideData(BaseModel):
    travel_guide: TravelGuide


class ModifyGuideRequest(BaseModel):
    action: UserAction


class GuideChangeData(BaseModel):
    travel_guide: TravelGuide
    version_lineage: VersionLineage
    conflicts: list[Conflict] = Field(default_factory=list)


class RefreshGuideRequest(BaseModel):
    expected_guide_version: int
    idempotency_key: str


class RefreshGuideData(BaseModel):
    travel_guide: TravelGuide
    version_lineage: VersionLineage
    refreshed_snapshot_id: str
