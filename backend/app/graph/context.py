"""LangGraph 每轮调用的运行期上下文。

`PlanState` 是契约对象（`CONTRACTS.md` §11），**不得新增字段**。
因此“本轮用户输入”和“本轮 MCP 检索到的原始候选”这两类**只在一轮内部有效**的数据
放在 `TurnContext` 里，通过 LangGraph 的 `Runtime` 传入节点，不进入契约状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import PlanningReadyDestination


@dataclass
class TurnContext:
    #: 本轮用户输入；None 表示不是由用户消息触发的推进
    user_message: str | None = None
    #: 本轮 `search_planning_ready_destinations` 的原始结果（尚未生成推荐）
    retrieved: list[PlanningReadyDestination] = field(default_factory=list)
