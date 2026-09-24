"""LangGraph 每轮调用的运行期上下文。

`PlanState` 是契约对象（`CONTRACTS.md` §10.2），**不得新增字段**。
因此“本轮用户输入”“本轮 MCP 检索到的原始候选”这类只在一轮内部有效的数据，
以及会话持有的 `TripProfileDraft`（§2.4 规定它不属于 `PlanState`），
都放在 `TurnContext` 里，通过 LangGraph 的 `Runtime` 传入节点。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.legacy import PlanningReadyDestination, TripProfileDraft


@dataclass
class TurnContext:
    #: 本轮用户输入；None 表示不是由用户消息触发的推进
    user_message: str | None = None
    #: 本轮 `search_planning_ready_destinations` 的原始结果（尚未生成推荐）
    retrieved: list[PlanningReadyDestination] = field(default_factory=list)
    #: 会话当前的不完整画像（`CONTRACTS.md` §2.4）。
    #: 它跨轮存在，但按契约不属于 `PlanState`，由会话存储持有，
    #: 每轮通过运行期上下文传入节点、结束后由调用方取回保存。
    draft: TripProfileDraft | None = None
