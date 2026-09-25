"""B 线单测用的假实现：不联网、不引入任何新依赖。

放在这里而不是各测试文件里，是为了让「模型返回什么」这类用例
只在一处维护 —— 测试重点是**我们怎么处理模型的输出**，
而不是模型本身说了什么。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas import Evidence, SearchTravelKnowledgeResponse
from app.schemas.v04.mcp import SearchTravelKnowledgeRequest
from app.llm.provider import LLMUnavailableError


class FakeLLMProvider:
    """按调用顺序吐预设负载的假模型。

    * `payloads`：依次返回的 JSON 对象；用完后再调用会抛 `LLMUnavailableError`
    * `available=False`：模拟「没配 Key」
    * `error=...`：每次调用都抛这个异常，模拟网络/服务失败
    """

    name = "fake"

    def __init__(
        self,
        *payloads: Mapping[str, Any],
        available: bool = True,
        error: BaseException | None = None,
    ) -> None:
        self._payloads: list[Mapping[str, Any]] = list(payloads)
        self._error = error
        self.is_available = available
        self.calls: list[dict[str, str]] = []

    def complete_json(
        self, *, system: str, user: str, max_retries: int | None = None
    ) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user})
        if not self.is_available:
            raise LLMUnavailableError("假模型已禁用")
        if self._error is not None:
            raise self._error
        if not self._payloads:
            raise LLMUnavailableError("假模型没有更多预设负载")
        return dict(self._payloads.pop(0))


class FakeKnowledgeProvider:
    """只返回预设证据的知识库，用于验证「没有证据就不给推荐」。"""

    def __init__(self, evidence: Mapping[str, Sequence[Evidence]]) -> None:
        self._evidence = {key: list(value) for key, value in evidence.items()}
        self.queries: list[str] = []

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeRequest
    ) -> SearchTravelKnowledgeResponse:
        items: list[Evidence] = []
        for destination_id in request.destination_ids or []:
            items.extend(self._evidence.get(destination_id, []))
        return SearchTravelKnowledgeResponse(evidence=items[: request.top_k])


def make_evidence(evidence_id: str, entity_id: str, content: str) -> Evidence:
    from datetime import datetime

    return Evidence(
        evidence_id=evidence_id,
        entity_id=entity_id,
        entity_type="DESTINATION",
        content=content,
        source_type="MOCK",
        source_ref=f"mock://{entity_id}",
        collected_at=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    )
