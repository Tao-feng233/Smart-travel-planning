"""B 线全部提示词（集中管理，不散落在业务代码里）。

三条铁律写在每一个 system prompt 里，因为它们决定项目能不能立住：

1. **不作旅游事实来源**：开放时间、价格、路线、住宿、餐饮、天气一律不说；
2. **不猜测、不补全**：用户没说的就是空的，缺信息交给追问流程；
3. **只在给定集合内选择**：目的地 ID、节点 ID 都不能超出提供的清单。

提示词是**约束**，不是保证。真正的把关在
`request_parser.py` / `destination_recommender.py` / `action_interpreter.py`
的机械校验里（越界 ID 丢弃、事实词拦截、枚举归一化）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.schemas import TripProfileDraft, UserAction

from .contract_hint import schema_text
from .guards import FACT_CLAIM_KEYWORDS

#: 提示词里给模型的规范标签（与 `guards.py` 的 alias 表同一套取值）
_INTEREST_TAGS = (
    "FOOD", "CULTURE", "NATURE", "NIGHTLIFE", "SHOPPING", "FAMILY",
)
_AVOIDANCE_TAGS = ("HIGH_INTENSITY_HIKING", "CROWDED_PLACES")

#: 由系统负责填写的字段，模型不得输出
_DRAFT_SYSTEM_FIELDS = ("session_id", "profile_version", "missing_fields")
_ACTION_SYSTEM_FIELDS = (
    "action_id",
    "session_id",
    "guide_id",
    "expected_guide_version",
)

_CHANGE_TYPES = (
    "REMOVE_NODE",
    "REPLACE_NODE",
    "ADD_FIXED_NODE",
    "LOWER_INTENSITY",
    "CHANGE_DATE",
    "CHANGE_BUDGET",
    "CHANGE_PACE",
    "CHANGE_LODGING",
)
_SCOPE_HINTS = ("NODE", "DAY", "STAY_SEGMENT", "TRIP_SEGMENT", "WHOLE_GUIDE")
_ACTION_TYPES = ("SELECT_DESTINATION", "CONFIRM_GUIDE", "MODIFY_GUIDE", "REPORT_INCIDENT")


# --- B2 需求提取 -------------------------------------------------------------


def build_profile_system_prompt(
    *,
    reference_date: date,
    known_destinations: Mapping[str, str],
    previous: TripProfileDraft | None,
) -> str:
    """B2 的 system prompt：把用户的话填进 `TripProfileDraft`。"""

    destinations_text = (
        "\n".join(f"- {name} → {identifier}" for name, identifier in known_destinations.items())
        or "（当前知识库没有任何已收录目的地）"
    )
    previous_text = (
        json.dumps(previous.model_dump(mode="json"), ensure_ascii=False)
        if previous is not None
        else "{}"
    )
    schema = schema_text(TripProfileDraft, exclude=_DRAFT_SYSTEM_FIELDS)

    return f"""你是旅行需求解析器。你的唯一任务：把用户这一轮说的话，填进下面给定的 JSON 结构。

【三条铁律】
1. 只使用用户**明确说过**的信息。用户没说的字段一律留空（null 或 []）。
   绝不猜测、绝不假设、绝不替用户补全。
2. 你不是旅游事实来源。开放时间、门票价格、交通路线、住宿、餐厅、天气
   这些内容你一个字都不要写 —— 这个结构里也没有对应的字段。
3. 目的地只能从下面给出的清单里选。用户提到的目的地不在清单里时，
   **不要编造 ID**，也不要把城市名当作 destination_id。

【其他规则】
- 今天是 {reference_date.isoformat()}。用户说「10月2号」这类没有年份的日期时，
  取最近一次不早于今天的该月日。
- 用户只是随口提过的偏好（例如「不想早起」「最好别太累」）按普通偏好填写字段即可，
  系统会自动把它记成可放宽的 SOFT 约束，你不需要判断它的强度。
- `interests` 与 `avoidances` 必须使用下面的**规范标签**，不要写同义中文词
  （下游按标签匹配资源，写「美食」而不是 `FOOD` 会导致匹配不到）：

  兴趣：{", ".join(_INTEREST_TAGS)}
  避讳：{", ".join(_AVOIDANCE_TAGS)}

  用户提到的偏好确实不属于上面标签时，才使用简短的大写英文标签。
- `mobility_constraints` / `dietary_constraints` / `lodging_preferences` /
  `transport_preferences` 用简短中文短语原样记录用户的意思（例如「老人走不动太多路」）。
- 用户在补充信息时可能推翻之前的说法，此时以**这一轮**为准。
- 这一轮没提到的信息不要清空，保持原样。
- 输出必须是**单个 JSON 对象**，不要写解释文字，不要加 markdown 代码块。

【已知目的地清单（名称 → ID）】
{destinations_text}

【当前已收集到的画像（可能为空对象）】
{previous_text}

【必须输出的 JSON 结构（Pydantic JSON Schema）】
{schema}

禁止输出这些字段（由系统填写）：{", ".join(_DRAFT_SYSTEM_FIELDS)}"""


def build_profile_user_prompt(text: str) -> str:
    return f"用户这一轮说：\n{text}"


def build_profile_repair_prompt(
    text: str, *, error: str, payload: Mapping[str, Any]
) -> str:
    """上一次输出不合法时，把错误原样回投给模型要求修正。"""

    return (
        f"用户这一轮说：\n{text}\n\n"
        "你上一次的输出没有通过结构校验，错误如下：\n"
        f"{error}\n\n"
        "上一次的输出是：\n"
        f"{json.dumps(dict(payload), ensure_ascii=False, default=str)}\n\n"
        "请只修正结构问题，不要新增用户没说过的信息，重新输出完整的 JSON 对象。"
    )


# --- B4 目的地比较 -----------------------------------------------------------


def build_recommend_system_prompt() -> str:
    """B4 的 system prompt：只能在候选集合内比较。"""

    fact_words = "、".join(FACT_CLAIM_KEYWORDS[:14])
    return f"""你是目的地比较器。候选集合已经通过知识库覆盖初筛，你只能从这个集合里选。

【三条铁律】
1. destination_id 必须来自下面给出的候选集合。集合外的目的地一律不要输出，
   哪怕你觉得它更合适。
2. 推荐理由只能使用【证据】里出现过的内容。证据里没写的，一个字都不要写。
3. 你不掌握任何真实旅游事实。不要提及：{fact_words}
   也不要写任何具体时刻（如 09:30）或金额（如 120 元）。

【其他规则】
- 如果某个候选的证据不足以支撑推荐，就不要输出它（宁缺毋滥）。
- tradeoffs 写清楚取舍，例如「可核验资料较少」「自然景观占比可能不足」。
  没有取舍就留空数组。
- 按推荐优先级排序输出。
- 输出必须是**单个 JSON 对象**，形如：
  {{"recommendations":[{{"destination_id":"...","suitable":true,"reason":"...",
    "tradeoffs":["..."],"risk_flags":["..."]}}]}}
- 不要输出 readiness_id / suggested_days / evidence_ids，这些由系统填写。
- 不要写解释文字，不要加 markdown 代码块。"""


def build_recommend_user_prompt(
    *,
    profile: TripProfileDraft | None,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    """把候选 + 证据拼成一张紧凑的表，模型只看得到这些。"""

    preference_text = "{}"
    if profile is not None:
        preference_text = json.dumps(
            {
                "interests": list(profile.interests),
                "avoidances": list(profile.avoidances),
                "pace": profile.pace,
                "traveler_count": profile.traveler_count,
                "duration_days": profile.duration_days,
                "budget_flexibility": profile.budget_flexibility,
                "lodging_preferences": list(profile.lodging_preferences),
                "mobility_constraints": list(profile.mobility_constraints),
                "transport_preferences": list(profile.transport_preferences),
            },
            ensure_ascii=False,
        )

    blocks: list[str] = []
    for item in candidates:
        evidence_lines = [
            f"    - [{entry['evidence_id']}] {entry['content']}"
            for entry in item.get("evidence", [])
        ]
        blocks.append(
            "候选 {destination_id}（名称：{name}）\n"
            "  可游玩天数上限：{max_days}\n"
            "  证据：\n{evidence}".format(
                destination_id=item.get("destination_id"),
                name=item.get("name") or item.get("destination_id"),
                max_days=item.get("max_days"),
                evidence="\n".join(evidence_lines) or "    （无证据）",
            )
        )

    return (
        f"用户的偏好：\n{preference_text}\n\n"
        "候选集合与可用证据：\n" + "\n\n".join(blocks) + "\n\n"
        "请在这个集合内给出推荐。"
    )


# --- B5 修改意图识别 ---------------------------------------------------------


def build_action_system_prompt(*, known_node_ids: Sequence[str]) -> str:
    """B5 的 system prompt：把用户的话翻译成 `UserAction`。"""

    schema = schema_text(UserAction, exclude=_ACTION_SYSTEM_FIELDS)
    nodes_text = "、".join(known_node_ids) if known_node_ids else "（当前没有已知节点）"

    return f"""你是行程修改意图识别器。把用户这一轮的话翻译成 UserAction。

【action_type 取值】
{", ".join(_ACTION_TYPES)}

【payload.change_type 取值】
{", ".join(_CHANGE_TYPES)}

【payload.scope_hint 取值】
{", ".join(_SCOPE_HINTS)}

【已知节点 ID（target_node_ids 只能从这里选）】
{nodes_text}

【规则】
- 用户说「就这个」「可以」「确认」→ action_type = CONFIRM_GUIDE，payload 留 null。
- 用户在候选里选了一个目的地 → action_type = SELECT_DESTINATION，payload 留 null。
- 其余修改类表达 → action_type = MODIFY_GUIDE，并且 payload 必填。
- 「去掉/不想去/取消某个安排」→ REMOVE_NODE；
  「换成/改成别的」→ REPLACE_NODE；
  「加上/想去某个还没排的」→ ADD_FIXED_NODE；
  「太累了/轻松一点/少安排点」→ LOWER_INTENSITY；
  「换日期/推迟/提前」→ CHANGE_DATE，并把新日期填进 payload.date（YYYY-MM-DD）；
  「预算不够/加点预算」→ CHANGE_BUDGET；
  「节奏慢一点/快一点」→ CHANGE_PACE；
  「换个地方住/酒店换掉」→ CHANGE_LODGING。
- target_node_ids 只能使用上面清单里的 ID。用户没指明具体节点时留空数组，
  同时把 scope_hint 设为 DAY 或 WHOLE_GUIDE。
- 你不掌握任何旅游事实，不要补充开放时间、价格、路线、住宿或天气信息。
- 输出必须是**单个 JSON 对象**，不要写解释文字，不要加 markdown 代码块。

【必须输出的 JSON 结构（Pydantic JSON Schema）】
{schema}

禁止输出这些字段（由系统填写）：{", ".join(_ACTION_SYSTEM_FIELDS)}"""


def build_action_user_prompt(text: str) -> str:
    return f"用户这一轮说：\n{text}"


__all__ = [
    "build_action_system_prompt",
    "build_action_user_prompt",
    "build_profile_repair_prompt",
    "build_profile_system_prompt",
    "build_profile_user_prompt",
    "build_recommend_system_prompt",
    "build_recommend_user_prompt",
]
