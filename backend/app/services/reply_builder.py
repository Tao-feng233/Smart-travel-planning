"""把 `PlanState` 翻译成面向用户的助手回复。

刻意做成**纯函数**：回复文案只由状态决定，不引入额外状态，
因此可以在测试里直接断言“缺日期时会问日期”。
"""

from __future__ import annotations

from typing import Callable, Mapping

from app.graph.stages import PlanStage
from app.schemas import AssistantReply, DestinationSuggestion, PlanState, ReplyKind

from .missing_fields import build_questions

_INSUFFICIENT_DATA_TEXT = (
    "当前知识库的数据覆盖不足，无法给出经过验证的推荐。"
    "可以尝试调整出行日期、缩小目的地范围，或补充偏好后重新提问。"
)


def build_reply(
    state: PlanState,
    *,
    name_lookup: Callable[[str], str | None] | None = None,
    data_is_mock: bool = False,
) -> AssistantReply:
    notes: list[str] = []
    if data_is_mock:
        notes.append(
            "当前数据源为模拟数据（MOCK_ONLY），仅用于流程验证，不代表真实旅游事实。"
        )

    stage = state.stage

    if stage == PlanStage.ASKING_CLARIFICATION.value:
        missing = state.profile.missing_fields if state.profile else []
        questions = build_questions(missing)
        return AssistantReply(
            kind=ReplyKind.QUESTION,
            text="为了给你推荐合适的目的地，还需要确认几件事：",
            questions=questions,
            missing_fields=missing,
            notes=notes,
        )

    if stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value:
        suggestions = [
            DestinationSuggestion(
                destination_id=item.destination_id,
                name=_resolve_name(item.destination_id, name_lookup),
                suggested_days=item.suggested_days,
                suitable=item.suitable,
                coverage_version=item.coverage_version,
                reason=item.reason,
                tradeoffs=item.tradeoffs,
                risk_flags=item.risk_flags,
                evidence_ids=item.evidence_ids,
            )
            for item in state.destination_candidates
        ]
        return AssistantReply(
            kind=ReplyKind.RECOMMENDATION,
            text="根据你的需求，从知识库覆盖达标的目的地中推荐以下候选，请选择想去的一个：",
            suggestions=suggestions,
            notes=notes,
        )

    if stage == PlanStage.INSUFFICIENT_DATA.value:
        return AssistantReply(
            kind=ReplyKind.INSUFFICIENT_DATA,
            text=_INSUFFICIENT_DATA_TEXT,
            missing_fields=state.profile.missing_fields if state.profile else [],
            notes=notes,
        )

    if stage == PlanStage.CREATED.value:
        return AssistantReply(
            kind=ReplyKind.INFO,
            text="会话已创建，请描述你的旅行需求，例如出发地、日期、人数和预算。",
            notes=notes,
        )

    return AssistantReply(
        kind=ReplyKind.INFO,
        text="已更新你的旅行需求。",
        missing_fields=state.profile.missing_fields if state.profile else [],
        notes=notes,
    )


def build_name_lookup(name_to_id: Mapping[str, str]) -> Callable[[str], str | None]:
    """由“名称 → ID”映射构造反向查询。"""

    inverted = {value: key for key, value in name_to_id.items()}
    return inverted.get


def _resolve_name(
    destination_id: str, name_lookup: Callable[[str], str | None] | None
) -> str:
    if name_lookup is not None:
        name = name_lookup(destination_id)
        if name:
            return name
    return destination_id
