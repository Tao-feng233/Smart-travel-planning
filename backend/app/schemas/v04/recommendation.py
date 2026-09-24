"""目的地推荐（`CONTRACTS.md` §6）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DestinationRecommendation(BaseModel):
    """LLM 推荐结果。

    `destination_id` 与 `readiness_id` 必须来自
    `search_planning_ready_destinations` 的返回集合，不得越界。
    """

    destination_id: str
    readiness_id: str
    suggested_days: int
    suitable: bool = True
    reason: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
