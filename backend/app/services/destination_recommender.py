"""目的地推荐（v0.4 契约）。

⚠️ **本文件是 STUB**。按分工，目的地比较与天数建议属于 B 线（B4），
真实实现应由 LLM 在**已通过覆盖初筛的候选集合内**完成比较，并只能返回
候选中存在的 `destination_id`（`CONTRACTS.md` §6）。

这里先用规则打分让 LangGraph 能推进到“推荐 → 等待用户确认”，
B 线完成后实现同一 `DestinationRecommender` 协议即可替换。

**不得违反的约束**：推荐理由只能引用 RAG 证据或 MCP 事实；
拿不到证据的目的地直接丢弃，不靠模型记忆编理由。
"""

from __future__ import annotations

from typing import Protocol, Sequence

from app.schemas import (
    DestinationRecommendation,
    PlanningReadinessEvaluation,
    SearchTravelKnowledgeRequest,
    SearchTravelKnowledgeResponse,
    TripProfile,
)

#: 偏好枚举 → 证据文本里的判断关键词。只用于**在已检索到的证据里**找依据。
_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FOOD": ("美食", "吃", "小吃", "餐厅"),
    "CULTURE": ("人文", "文化", "历史", "博物馆"),
    "NATURE": ("自然", "风景", "山水", "公园"),
    "NIGHTLIFE": ("夜生活", "夜景"),
    "SHOPPING": ("购物", "逛街"),
}


class KnowledgeProvider(Protocol):
    """推荐时需要的证据检索能力（A 线 MCP Server 的一个工具）。"""

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeRequest
    ) -> SearchTravelKnowledgeResponse: ...


class DestinationRecommender(Protocol):
    """B4 的替换点。"""

    def recommend(
        self,
        *,
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        readiness: Sequence[PlanningReadinessEvaluation],
        mcp: KnowledgeProvider,
    ) -> list[DestinationRecommendation]: ...


class StubDestinationRecommender:
    """规则式推荐（STUB，待 B 线替换）。"""

    def __init__(self, max_results: int = 3) -> None:
        self._max_results = max_results

    def recommend(
        self,
        *,
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        readiness: Sequence[PlanningReadinessEvaluation],
        mcp: KnowledgeProvider,
    ) -> list[DestinationRecommendation]:
        wanted = self._wanted_tags(profile)
        readiness_by_id = {item.destination_id: item for item in readiness}
        scored: list[tuple[int, DestinationRecommendation]] = []

        for candidate in candidates:
            evidence = mcp.search_travel_knowledge(
                SearchTravelKnowledgeRequest(
                    query="目的地认知与体验特点",
                    destination_ids=[candidate.destination_id],
                    top_k=3,
                )
            )
            if not evidence.evidence:
                # 没有证据就不给出推荐理由，避免让模型用记忆补全事实
                continue

            text = " ".join(item.content for item in evidence.evidence)
            matched = {tag for tag, words in _TAG_KEYWORDS.items() if any(w in text for w in words)}
            hits = sorted(matched & wanted)
            evaluation = readiness_by_id.get(candidate.destination_id)

            score = len(hits) * 10
            if profile is not None and any(
                item.fixed and item.destination_id == candidate.destination_id
                for item in profile.destination_requests
            ):
                score += 100
            if not wanted:
                score += 1

            reason_parts: list[str] = []
            if hits:
                reason_parts.append("匹配你的偏好：" + "、".join(hits))
            if evaluation is not None:
                reason_parts.append(
                    f"覆盖达标（就绪度 {evaluation.readiness_id}，"
                    f"规则版本 {evaluation.ruleset_version}）"
                )

            evidence_ids = [item.evidence_id for item in evidence.evidence]
            scored.append(
                (
                    score,
                    DestinationRecommendation(
                        destination_id=candidate.destination_id,
                        readiness_id=candidate.readiness_id,
                        suggested_days=self._suggest_days(profile, candidate),
                        suitable=True,
                        reason="；".join(reason_parts) or None,
                        tradeoffs=self._tradeoffs(evidence, matched),
                        risk_flags=["LIMITED_EVIDENCE"] if len(evidence_ids) < 2 else [],
                        evidence_ids=evidence_ids,
                    ),
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[: self._max_results]]

    @staticmethod
    def _wanted_tags(profile: TripProfile | None) -> set[str]:
        if profile is None:
            return set()
        wanted = set(profile.interests)
        joined = " ".join([*profile.avoidances, *profile.lodging_preferences, profile.pace or ""])
        for tag, words in _TAG_KEYWORDS.items():
            if any(word in joined for word in words):
                wanted.add(tag)
        return wanted

    @staticmethod
    def _suggest_days(
        profile: TripProfile | None, candidate: DestinationRecommendation
    ) -> int:
        suggested = max(1, candidate.suggested_days)
        if profile is None:
            return suggested
        return max(1, min(suggested, profile.duration_days))

    @staticmethod
    def _tradeoffs(
        evidence: SearchTravelKnowledgeResponse, matched: set[str]
    ) -> list[str]:
        tradeoffs: list[str] = []
        if len(evidence.evidence) < 2:
            tradeoffs.append("可核验的认知资料较少，细节可能需要现场确认")
        if "NATURE" not in matched:
            tradeoffs.append("自然景观占比可能不足")
        return tradeoffs
