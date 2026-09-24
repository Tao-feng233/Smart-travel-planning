"""B4：在已通过覆盖初筛的候选集合内做目的地比较（LLM 正式实现）。

替换点：`app.services.destination_recommender.DestinationRecommender` 协议。
`StubDestinationRecommender` 保留为降级出口。

为什么这一层要这么严：`AGENTS.md` 写着「LLM 只能选择候选集合中存在的实体ID」，
而目的地推荐是用户看到的**第一个**决策结果 —— 一旦这里放出去一个集合外的
目的地、或一段编造的理由，后面整条链路的事实可信度就没了。所以：

* 集合外的 `destination_id` → 丢弃该条（不是替换、不是修正）；
* 理由里出现开放时间/票价/里程/天气这类**事实词或具体数字** → 丢弃该条推荐；
* `evidence_ids` / `readiness_id` / `suggested_days` **一律由系统填**，不采信模型；
* 整批都不可用时降级到 STUB，而不是让流程空转。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.schemas import (
    DestinationRecommendation,
    PlanningReadinessEvaluation,
    SearchTravelKnowledgeRequest,
    TripProfile,
)
from app.services.destination_recommender import (
    DestinationRecommender,
    KnowledgeProvider,
    StubDestinationRecommender,
)

from .guards import find_fact_claims, normalize_string_list
from .prompts import build_recommend_system_prompt, build_recommend_user_prompt
from .provider import LLMProvider

logger = logging.getLogger(__name__)

#: 证据少于这个条数时给候选打上「资料有限」风险标记
THIN_EVIDENCE_THRESHOLD = 2


@dataclass(frozen=True)
class RecommendOutcome:
    recommendations: list[DestinationRecommendation]
    used_llm: bool
    diagnostics: tuple[str, ...] = ()


@dataclass
class LLMDestinationRecommender:
    provider: LLMProvider
    fallback: DestinationRecommender = field(default_factory=StubDestinationRecommender)
    max_results: int = 3
    evidence_top_k: int = 3

    def recommend(
        self,
        *,
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        readiness: Sequence[PlanningReadinessEvaluation],
        mcp: KnowledgeProvider,
    ) -> list[DestinationRecommendation]:
        return self.recommend_with_diagnostics(
            profile=profile,
            candidates=candidates,
            readiness=readiness,
            mcp=mcp,
        ).recommendations

    def recommend_with_diagnostics(
        self,
        *,
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        readiness: Sequence[PlanningReadinessEvaluation],
        mcp: KnowledgeProvider,
    ) -> RecommendOutcome:
        blocks, evidence_by_destination = self._collect_evidence(
            candidates=candidates, mcp=mcp
        )
        if not blocks:
            # 一个候选都拿不到证据：明确不给推荐，绝不靠模型记忆补（与 STUB 同口径）
            return RecommendOutcome(
                recommendations=[],
                used_llm=False,
                diagnostics=("所有候选都检索不到可核验证据，按「资料不足」处理",),
            )

        if not self.provider.is_available:
            return self._degrade(
                profile=profile,
                candidates=candidates,
                readiness=readiness,
                mcp=mcp,
                reason=f"LLM 未配置（{self.provider.name}），已降级为规则式推荐",
            )

        try:
            payload = self.provider.complete_json(
                system=build_recommend_system_prompt(),
                user=build_recommend_user_prompt(profile=profile, candidates=blocks),
            )
        except Exception as exc:  # noqa: BLE001
            # 同 B2：模型通道的任何失败都走降级，不让用户请求崩掉
            return self._degrade(
                profile=profile,
                candidates=candidates,
                readiness=readiness,
                mcp=mcp,
                reason=f"LLM 调用失败（{type(exc).__name__}: {exc}），已降级为规则式推荐",
            )

        result, diagnostics = self._validate_payload(
            payload=payload,
            profile=profile,
            candidates=candidates,
            evidence_by_destination=evidence_by_destination,
        )
        if not result:
            return self._degrade(
                profile=profile,
                candidates=candidates,
                readiness=readiness,
                mcp=mcp,
                reason="模型给出的推荐全部不合规（越界 ID 或理由含未经核验的事实）",
                extra=tuple(diagnostics),
            )
        return RecommendOutcome(
            recommendations=result, used_llm=True, diagnostics=tuple(diagnostics)
        )

    # --- 内部 ---------------------------------------------------------------

    def _collect_evidence(
        self,
        *,
        candidates: Sequence[DestinationRecommendation],
        mcp: KnowledgeProvider,
    ) -> tuple[list[dict[str, Any]], dict[str, list[Mapping[str, Any]]]]:
        """按候选逐个取证据；取不到证据的候选不进提示词（也不进结果）。"""

        blocks: list[dict[str, Any]] = []
        evidence_by_destination: dict[str, list[Mapping[str, Any]]] = {}

        for candidate in candidates:
            response = mcp.search_travel_knowledge(
                SearchTravelKnowledgeRequest(
                    query="目的地认知与体验特点",
                    destination_ids=[candidate.destination_id],
                    top_k=self.evidence_top_k,
                )
            )
            entries = [
                {"evidence_id": item.evidence_id, "content": item.content}
                for item in response.evidence
            ]
            if not entries:
                continue
            evidence_by_destination[candidate.destination_id] = entries
            blocks.append(
                {
                    "destination_id": candidate.destination_id,
                    "name": None,
                    "max_days": candidate.suggested_days,
                    "evidence": entries,
                }
            )
        return blocks, evidence_by_destination

    def _validate_payload(
        self,
        *,
        payload: Mapping[str, Any],
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        evidence_by_destination: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> tuple[list[DestinationRecommendation], list[str]]:
        diagnostics: list[str] = []
        candidate_by_id = {item.destination_id: item for item in candidates}
        raw_items = payload.get("recommendations")
        if not isinstance(raw_items, list):
            return [], ["模型输出的 recommendations 不是数组"]

        accepted: list[DestinationRecommendation] = []
        seen: set[str] = set()

        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            identifier = str(item.get("destination_id") or "").strip()
            if identifier not in candidate_by_id:
                diagnostics.append(
                    f"模型推荐了候选集合外的目的地 {identifier or '<空>'}，已丢弃该条"
                )
                continue
            if identifier in seen:
                diagnostics.append(f"目的地 {identifier} 被重复推荐，已去重")
                continue

            reason = _clean_text(item.get("reason"))
            if not reason:
                diagnostics.append(f"目的地 {identifier} 的推荐没有理由，已丢弃该条")
                continue

            hits = find_fact_claims(reason)
            if hits:
                diagnostics.append(
                    f"目的地 {identifier} 的推荐理由含未经核验的事实表述"
                    f"（{'、'.join(hits[:4])}），已丢弃该条"
                )
                continue

            tradeoffs = self._clean_tradeoffs(item.get("tradeoffs"), identifier, diagnostics)
            risk_flags = normalize_string_list(item.get("risk_flags"), max_items=6, max_length=30)
            evidence_ids = [
                str(entry["evidence_id"])
                for entry in evidence_by_destination.get(identifier, ())
            ]
            if len(evidence_ids) < THIN_EVIDENCE_THRESHOLD and "LIMITED_EVIDENCE" not in risk_flags:
                risk_flags.append("LIMITED_EVIDENCE")

            candidate = candidate_by_id[identifier]
            accepted.append(
                DestinationRecommendation(
                    destination_id=identifier,
                    readiness_id=candidate.readiness_id,
                    suggested_days=self._clamp_days(candidate.suggested_days, profile),
                    suitable=bool(item.get("suitable", True)),
                    reason=reason,
                    tradeoffs=tradeoffs,
                    risk_flags=risk_flags,
                    evidence_ids=evidence_ids,
                )
            )
            seen.add(identifier)
            if len(accepted) >= self.max_results:
                break

        return accepted, diagnostics

    @staticmethod
    def _clean_tradeoffs(
        raw: Any, identifier: str, diagnostics: list[str]
    ) -> list[str]:
        """取舍里同样不许夹带事实；命中的条目单独丢掉，不牵连整条推荐。"""

        cleaned: list[str] = []
        for text in normalize_string_list(raw, max_items=5, max_length=60):
            hits = find_fact_claims(text)
            if hits:
                diagnostics.append(
                    f"目的地 {identifier} 的一条取舍含事实表述（{'、'.join(hits[:3])}），已丢弃该条取舍"
                )
                continue
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _clamp_days(suggested: int, profile: TripProfile | None) -> int:
        days = max(1, int(suggested))
        if profile is None:
            return days
        return max(1, min(days, profile.duration_days))

    def _degrade(
        self,
        *,
        profile: TripProfile | None,
        candidates: Sequence[DestinationRecommendation],
        readiness: Sequence[PlanningReadinessEvaluation],
        mcp: KnowledgeProvider,
        reason: str,
        extra: Sequence[str] = (),
    ) -> RecommendOutcome:
        logger.info("B4 降级为规则式推荐：%s", reason)
        return RecommendOutcome(
            recommendations=list(
                self.fallback.recommend(
                    profile=profile,
                    candidates=candidates,
                    readiness=readiness,
                    mcp=mcp,
                )
            ),
            used_llm=False,
            diagnostics=(reason, *extra),
        )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["LLMDestinationRecommender", "RecommendOutcome"]
