"""REST 传输对象。

这些对象描述 HTTP 接口的请求/响应体，**不是** `CONTRACTS.md` 里的领域契约对象。
它们只做两件事：

1. 把 `PlanState` 包一层，便于前端读取；
2. 给出 C 线根据当前状态生成的**助手回复**结构。

领域数据一律复用 `contracts.py` / `guide.py`，不在这里重复定义。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .contracts import ContractModel, PlanState


class ReplyKind(str, Enum):
    """助手回复的类型，前端据此决定渲染成追问、候选卡片还是提示。"""

    QUESTION = "QUESTION"
    RECOMMENDATION = "RECOMMENDATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INFO = "INFO"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


class DestinationSuggestion(ContractModel):
    """推荐候选的展示用视图（数据来自 `DestinationRecommendation`）。"""

    destination_id: str
    name: str
    suggested_days: int
    suitable: bool = True
    coverage_version: str | None = None
    reason: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AssistantReply(ContractModel):
    kind: ReplyKind
    text: str
    questions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    suggestions: list[DestinationSuggestion] = Field(default_factory=list)
    #: 降级说明，例如“当前使用模拟数据”。前端必须展示，不得静默隐藏。
    notes: list[str] = Field(default_factory=list)


class CreateSessionRequest(ContractModel):
    #: 不传则服务端生成
    session_id: str | None = None


class CreateSessionResponse(ContractModel):
    session_id: str
    stage: str
    state: PlanState


class SendMessageRequest(ContractModel):
    text: str


class SendMessageResponse(ContractModel):
    session_id: str
    stage: str
    awaiting_user_input: bool
    reply: AssistantReply
    state: PlanState


class SessionStateResponse(ContractModel):
    session_id: str
    stage: str
    awaiting_user_input: bool
    reply: AssistantReply
    state: PlanState
