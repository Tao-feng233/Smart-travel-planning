"""把 `PlanState` + 本轮上下文翻译成面向用户的回复（v0.4 契约）。

刻意做成**纯函数**：回复文案只由状态与上下文决定，不引入额外状态，
因此可以在测试里直接断言“缺日期时会问日期”“排除过资源会说明原因”。

输出是 `CONTRACTS.md` §13.1 的 `SendMessageData`：

```text
stage, assistant_message, trip_profile?, destination_candidates?,
guide_id?, conflicts?, degraded_items?
```

⚠️ v0.4 没有结构化的"追问清单"字段，缺字段只能写进 `assistant_message`；
已登记在 `docs/contract-open-questions.md` 5.3。
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from app.graph.stages import PlanStage
from app.schemas import (
    Conflict,
    DestinationRecommendation,
    ItineraryPlan,
    PlanValidationStatus,
    PlanState,
    SendMessageData,
    TripProfile,
    TripProfileDraft,
    WarningItem,
)
from app.services.availability_filter import TripFilterResult

from .missing_fields import build_questions

_INSUFFICIENT_DATA_TEXT = (
    "当前知识库的数据覆盖不足，无法给出经过验证的推荐。"
    "可以尝试调整出行日期、缩小目的地范围，或补充偏好后重新提问。"
)

_CREATED_TEXT = "会话已创建，请描述你的旅行需求，例如出发地、日期、人数和预算。"

#: 模拟数据必须显式告知，不得静默当成真实数据（`CONTRACTS.md` §14 不变量 5）
_MOCK_NOTICE = "当前数据源为模拟数据（MOCK_ONLY），仅用于流程验证，不代表真实旅游事实。"

#: C4 排程缺输入时，把内部代码翻成用户能看懂的原因
_MISSING_INPUT_TEXT = {
    "LODGING_CANDIDATES": "住宿候选数据还没有到位，暂时生成不了含过夜的完整行程。",
    "MULTI_DESTINATION_P1": "多目的地规划属于 P1，当前只支持单目的地。",
}


def build_reply(
    state: PlanState,
    *,
    draft: TripProfileDraft | None = None,
    profile: TripProfile | None = None,
    recommendations: Sequence[DestinationRecommendation] = (),
    filter_result: TripFilterResult | None = None,
    plan: ItineraryPlan | None = None,
    plan_conflicts: Sequence[Conflict] = (),
    missing_inputs: Sequence[str] = (),
    name_lookup: Callable[[str], str | None] | None = None,
    data_is_mock: bool = False,
) -> SendMessageData:
    """按当前阶段生成面向用户的回复。"""

    stage = state.stage
    degraded: list[str] = []
    # 模拟数据这件事只讲一次：放在统一信封的 `warnings`
    # （`MOCK_DATA_IN_DEMO`，带 code 可判定，见 `build_warnings`）。
    # `degraded_items` 只放"本轮额外降级项"（例如关键事实未知的资源），
    # 两边重复同一句话会让前端把同一个问题显示两三遍。
    if filter_result is not None:
        degraded.extend(_unknown_notes(filter_result, name_lookup))

    if stage == PlanStage.ASKING_CLARIFICATION.value:
        missing = draft.compute_missing_fields() if draft is not None else []
        questions = build_questions(missing)
        lines = ["为了给你推荐合适的目的地，还需要确认几件事："]
        lines.extend(f"{index}. {question}" for index, question in enumerate(questions, 1))
        return SendMessageData(
            stage=stage,
            assistant_message="\n".join(lines),
            trip_profile=profile,
            degraded_items=degraded,
        )

    if stage in (
        PlanStage.AWAITING_DESTINATION_CONFIRMATION.value,
        PlanStage.RECOMMENDING_DESTINATIONS.value,
    ):
        lines: list[str] = []
        if recommendations:
            lines.append("根据你的需求，从知识库覆盖达标的目的地中推荐以下候选：")
            for item in recommendations:
                name = _resolve_name(item.destination_id, name_lookup)
                detail = f"建议 {item.suggested_days} 天"
                if item.reason:
                    detail = f"{detail}；{item.reason}"
                lines.append(f"- {name}（{detail}）")
        if filter_result is not None:
            lines.extend(_filter_lines(state, filter_result, name_lookup))
        if lines and state.stage == PlanStage.AWAITING_DESTINATION_CONFIRMATION.value:
            lines.append("确认后我就按这些资源排行程（回复「确认」即可）。")
        if not lines:
            lines.append(
                "请选择你想去的目的地；确定后回复「确认」，我再继续为你安排行程。"
            )
        return SendMessageData(
            stage=stage,
            assistant_message="\n".join(lines),
            trip_profile=profile,
            destination_candidates=list(recommendations),
            degraded_items=degraded,
        )

    if stage in (
        PlanStage.PLANNING.value,
        PlanStage.READY.value,
        PlanStage.REPAIRING.value,
    ) and plan is not None:
        return SendMessageData(
            stage=stage,
            assistant_message=_plan_text(plan, plan_conflicts),
            trip_profile=profile,
            conflicts=list(plan_conflicts),
            degraded_items=degraded,
        )

    if stage == PlanStage.INSUFFICIENT_DATA.value:
        # C4 排程缺关键输入时要说清缺什么，不能只丢一句"资料不足"
        reasons = [_MISSING_INPUT_TEXT[item] for item in missing_inputs if item in _MISSING_INPUT_TEXT]
        degraded.extend(reasons)
        text = _INSUFFICIENT_DATA_TEXT
        if reasons:
            text = text + "\n" + "\n".join(f"- {item}" for item in reasons)
        return SendMessageData(
            stage=stage,
            assistant_message=text,
            trip_profile=profile,
            degraded_items=degraded,
        )

    if stage == PlanStage.CREATED.value:
        return SendMessageData(
            stage=stage,
            assistant_message=_CREATED_TEXT,
            trip_profile=profile,
            degraded_items=degraded,
        )

    missing = draft.compute_missing_fields() if draft is not None else []
    questions = build_questions(missing)
    text = "已更新你的旅行需求。"
    if questions:
        text = text + "还需要确认：" + "；".join(questions)
    return SendMessageData(
        stage=stage,
        assistant_message=text,
        trip_profile=profile,
        destination_candidates=list(recommendations),
        degraded_items=degraded,
    )


def build_warnings(
    state: PlanState,
    *,
    draft: TripProfileDraft | None = None,
    data_is_mock: bool = False,
) -> list[WarningItem]:
    """统一信封里的 `warnings`：模拟数据与非阻塞的缺失字段提示。

    缺失字段属于正常工作流状态，不是 HTTP 错误（`CONTRACTS.md` §13）。
    """

    warnings: list[WarningItem] = []
    if data_is_mock:
        warnings.append(
            WarningItem(code="MOCK_DATA_IN_DEMO", message=_MOCK_NOTICE)
        )
    missing = draft.compute_missing_fields() if draft is not None else []
    if missing:
        warnings.append(
            WarningItem(
                code="MISSING_PROFILE_FIELDS",
                message="关键信息还不完整，请按追问补充。",
                details={name: name for name in missing},
            )
        )
    if state.stage == PlanStage.INSUFFICIENT_DATA.value:
        warnings.append(
            WarningItem(
                code="OUT_OF_KNOWLEDGE_COVERAGE",
                message="该需求超出当前知识库覆盖范围。",
            )
        )
    return warnings


def build_name_lookup(name_to_id: Mapping[str, str]) -> Callable[[str], str | None]:
    """由“名称 → ID”映射构造反向查询。"""

    inverted = {value: key for key, value in name_to_id.items()}
    return inverted.get


def _filter_lines(
    state: PlanState,
    result: TripFilterResult,
    name_lookup: Callable[[str], str | None] | None,
) -> list[str]:
    """说明前置过滤结果：排除了什么、为什么，绝不静默丢弃。"""

    if not state.resource_candidate_ids and not result.excluded:
        return []
    lines = [
        f"已按行程日期完成前置过滤：{len(result.plannable)} 个可用资源"
        f"（无条件主方案 {len(result.usable)} 个、有条件 {len(result.conditional)} 个），"
        f"排除 {len(result.excluded)} 个。"
    ]
    for item in result.excluded:
        lines.append(f"- 已排除 {item.resource_id}：{item.reason}")
    for resource_id, dates in result.unavailable_dates.items():
        joined = "、".join(day.isoformat() for day in dates)
        lines.append(f"- {resource_id} 在这些日期不可用，不得排入：{joined}")
    return lines


def _unknown_notes(
    result: TripFilterResult,
    name_lookup: Callable[[str], str | None] | None,
) -> list[str]:
    if not result.unknown:
        return []
    ids = "、".join(item.resource_id for item in result.unknown)
    return [f"以下资源的关键事实未知，不能作为主方案：{ids}"]


def _plan_text(plan: ItineraryPlan, conflicts: Sequence[Conflict]) -> str:
    """把 C4 的计划翻成用户能看懂的一段话（不暴露内部 ID 细节）。"""

    summary = plan.budget_summary
    attractions = len([item for item in plan.nodes if item.node_type == "ATTRACTION"])
    meals = len([item for item in plan.nodes if item.node_type == "MEAL"])
    lines = [
        f"行程已排好（第 {plan.plan_version} 版，共 {len(plan.days)} 天）：",
        f"- 日期：{plan.start_date.isoformat()} ~ {plan.end_date.isoformat()}",
    ]
    if plan.stay_segments:
        stay = plan.stay_segments[0]
        lines.append(
            f"- 住宿：{stay.lodging_area}"
            f"（{stay.check_in_date.isoformat()} 入住，{stay.check_out_date.isoformat()} 退房）"
        )
    lines.append(
        f"- 安排：{attractions} 个游玩地点、{meals} 次用餐、{len(plan.travel_legs)} 段交通"
    )
    lines.append(
        f"- 预算：预计 ¥{summary.estimated_min_total:.0f} ~ "
        f"¥{summary.estimated_max_total:.0f}（上限 ¥{summary.total_limit:.0f}，"
        f"剩余 ¥{summary.remaining_min:.0f} 起）"
    )
    errors = [item for item in conflicts if item.severity == "ERROR"]
    warnings = [item for item in conflicts if item.severity != "ERROR"]
    if plan.plan_validation_status == PlanValidationStatus.VALID:
        lines.append(
            f"- 验证结论：**通过**（{len(warnings)} 项提醒）"
            if warnings
            else "- 验证结论：**通过**。"
        )
    elif plan.plan_validation_status == PlanValidationStatus.INVALID:
        lines.append(f"- 验证结论：**未通过**，有 {len(errors)} 项必须处理：")
        lines.extend(f"  · {item.message}" for item in errors[:3])
        lines.append("  自动修复（闭馆替换等）在 C6 接入后重跑验证。")
    else:
        lines.append("- 验证还没跑（`plan_validation_status = PENDING`）。")
    if warnings and plan.plan_validation_status != PlanValidationStatus.VALID:
        lines.append(f"- 另有 {len(warnings)} 项提醒：")
        lines.extend(f"  · {item.message}" for item in warnings[:3])
    elif warnings:
        lines.extend(f"  · {item.message}" for item in warnings[:3])
    return "\n".join(lines)


def _resolve_name(
    destination_id: str, name_lookup: Callable[[str], str | None] | None
) -> str:
    if name_lookup is not None:
        name = name_lookup(destination_id)
        if name:
            return name
    return destination_id
