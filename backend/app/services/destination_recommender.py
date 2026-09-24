"""目的地推荐。

⚠️ **本文件是 STUB**。按分工，目的地比较与天数建议属于 B 线（B4），
真实实现应由 LLM 在**已通过硬条件初筛的候选集合内**完成比较，并只能返回
候选中存在的 `destination_id`（`CONTRACTS.md` §4）。

这里先用规则打分让 LangGraph 能推进到“推荐 → 等待用户确认”，
B 线完成后实现同一 `DestinationRecommender` 协议即可替换。
"""

from __future__ import annotations

from typing import Protocol

from app.schemas import DestinationRecommendation, PlanningReadyDestination, TripProfile

from . import fake_data
from .travel_mcp_client import TravelMCPClient

_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FOOD": ("美食", "吃", "小吃"),
    "CULTURE": ("人文", "文化", "历史", "博物馆"),
    "NATURE": ("自然", "风景", "山水", "公园"),
    "NIGHTLIFE": ("夜生活", "夜景"),
    "SHOPPING": ("购物", "逛街"),
}


class DestinationRecommender(Protocol):
    def recommend(
        self,
        *,
        profile: TripProfile | None,
        candidates: list[PlanningReadyDestination],
        mcp: TravelMCPClient,
    ) -> list[DestinationRecommendation]: ...


class StubDestinationRecommender:
    """规则式推荐（STUB，待 B 线替换）。"""

    def __init__(self, max_results: int = 3) -> None:
        self._max_results = max_results

    def recommend(
        self,
        *,
        profile: TripProfile | None,
        candidates: list[PlanningReadyDestination],
        mcp: TravelMCPClient,
    ) -> list[DestinationRecommendation]:
        wanted = self._wanted_tags(profile)
        scored: list[tuple[int, DestinationRecommendation]] = []
        for candidate in candidates:
            meta = fake_data.find_destination(candidate.destination_id) or {}
            tags = set(meta.get("experience_tags", []))
            score = len(tags & wanted) * 10
            if not wanted:
                score = 1
            coverage = candidate.coverage
            reason_parts = []
            if tags & wanted:
                reason_parts.append(
                    "匹配你的偏好：" + "、".join(sorted(tags & wanted))
                )
            if coverage is not None:
                reason_parts.append(
                    f"知识覆盖度 {coverage.visit_place_count} 个游玩地点"
                    f"（覆盖版本 {coverage.coverage_version}）"
                )
            evidence = mcp.search_travel_knowledge(
                _knowledge_request(candidate.destination_id)
            )
            evidence_ids = [item.evidence_id for item in evidence.evidence]
            if not evidence_ids:
                # 没有证据就不给出推荐理由，避免让模型用记忆补全事实
                continue
            scored.append(
                (
                    score,
                    DestinationRecommendation(
                        destination_id=candidate.destination_id,
                        suggested_days=self._suggest_days(profile, meta),
                        coverage_version=candidate.coverage_version,
                        suitable=True,
                        reason="；".join(reason_parts) or None,
                        tradeoffs=self._tradeoffs(meta, coverage),
                        risk_flags=self._risk_flags(profile, meta, coverage),
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
        joined = " ".join(profile.soft_preferences) + " " + (profile.pace or "")
        for tag, words in _TAG_KEYWORDS.items():
            if any(word in joined for word in words):
                wanted.add(tag)
        return wanted

    @staticmethod
    def _suggest_days(profile: TripProfile | None, meta: dict) -> int:
        minimum = meta.get("recommended_min_days", 1)
        maximum = meta.get("recommended_max_days", minimum)
        duration = profile.duration_days if profile else None
        if duration is None:
            return max(minimum, min(maximum, 3))
        return max(minimum, min(maximum, duration))

    @staticmethod
    def _tradeoffs(meta: dict, coverage) -> list[str]:
        tradeoffs: list[str] = []
        if coverage is not None and coverage.restaurant_coverage < 0.6:
            tradeoffs.append("具体餐厅数据覆盖有限，部分用餐只能给到区域与类型建议")
        if coverage is not None and coverage.intercity_transport_coverage < 0.7:
            tradeoffs.append("城际交通只有典型耗时与价格区间，没有实时班次")
        if "NATURE" not in set(meta.get("experience_tags", [])):
            tradeoffs.append("自然景观占比相对较低")
        return tradeoffs

    @staticmethod
    def _risk_flags(profile: TripProfile | None, meta: dict, coverage) -> list[str]:
        flags: list[str] = []
        duration = profile.duration_days if profile else None
        maximum = meta.get("recommended_max_days")
        if duration and maximum and duration > maximum:
            flags.append("DAYS_EXCEED_RECOMMENDED")
        if coverage is not None and coverage.visit_place_count < 10:
            flags.append("LIMITED_VISIT_PLACES")
        return flags


def _knowledge_request(destination_id: str):
    from app.schemas import SearchTravelKnowledgeInput

    return SearchTravelKnowledgeInput(
        query="目的地认知与体验特点",
        province=None,
        destination_ids=[destination_id],
        resource_type=None,
        top_k=3,
    )
