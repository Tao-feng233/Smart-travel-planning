"""B 线全部提示词（集中管理，不散落在业务代码里）。

三条铁律写在每一个 system prompt 里，因为它们决定项目能不能立住：

1. **不作旅游事实来源**：开放时间、价格、路线、住宿、餐饮、天气一律不说；
2. **不猜测、不补全**：用户没说的就是空的，缺信息交给追问流程；
3. **只在给定集合内选择**：目的地 ID、节点 ID 都不能超出提供的清单。

提示词是**约束**，不是保证。真正的把关在
`request_parser.py` / `destination_recommender.py` / `action_interpreter.py`
的机械校验里（越界 ID 丢弃、事实词拦截、枚举归一化）。

版本：``PROMPT_VERSION``（见下）。提示词是工程产物：每次改动必须
① 更新版本号与下方变更记录；② 跑 `backend/tests/test_prompt_regression.py`
回归集，防止「修好 A 弄坏 B」。

变更记录
--------
- prompts-2026-09-28-v2：补 few-shot 示例（B2×2 / B4×1 / B5×3，全部为
  模块级常量，回归测试直接引用并校验其合法性）；负向表述改正向
  （「只输出/只取自」替代「不要/绝不能」）；B5 增加 action_type
  决策清单，把「何时算修改已有攻略」写成显式判断信号；B2 精简重复规则。
- prompts-2026-09-24-v1：初版（三条铁律 + JSON Schema 约束输出）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.schemas import TripProfileDraft, UserAction

from .contract_hint import schema_text
from .guards import FACT_CLAIM_KEYWORDS

#: 当前提示词版本（改动提示词必须同步改这里 + 上方变更记录）
PROMPT_VERSION = "prompts-2026-09-28-v2"

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


# --- few-shot 示例（工程产物） -------------------------------------------------
#
# 这些是**模块级常量**而不是写在字符串里的散文：`test_prompt_regression.py`
# 直接引用它们做契约校验，保证示例本身永远合法。改示例 = 改测试期望，一起改。

#: B2 示例：(用户输入, 期望输出, 讲解)。输出只含模型该填的字段。
B2_FEWSHOT_EXAMPLES: tuple[tuple[str, dict[str, Any], str], ...] = (
    (
        "我和朋友两人从成都出发，想玩5天，预算八千，爱吃爱逛古镇",
        {
            "departure_city": "成都",
            "duration_days": 5,
            "traveler_count": 2,
            "budget": {"amount": 8000, "currency": "CNY"},
            "interests": ["FOOD", "CULTURE"],
        },
        "天数、预算、人数都明说了才填；用户没点名目的地，destination_requests 保持空数组。",
    ),
    (
        "我想带爸妈出去走走，他们腿脚不好，别太累",
        {
            "traveler_count": 3,
            "mobility_constraints": ["爸妈腿脚不好，别太累"],
        },
        "日期、天数、预算都没说，全部留空（不出现这些字段），交给系统的追问流程。",
    ),
)

#: B4 示例：场景描述 + 期望输出 + 讲解。
B4_FEWSHOT_EXAMPLE: dict[str, Any] = {
    "scenario": (
        "候选 dest_a 的证据写着「古镇保存完好，建筑集中」「公共交通可达」；"
        "候选 dest_b 没有任何证据。用户偏好 CULTURE。"
    ),
    "output": {
        "recommendations": [
            {
                "destination_id": "dest_a",
                "suitable": True,
                "reason": "用户偏好 CULTURE，证据显示该地古镇与建筑集中，且公共交通可达。",
                "tradeoffs": [],
                "risk_flags": [],
            }
        ]
    },
    "note": "dest_b 没有证据，按「宁缺毋滥」不输出。",
}

#: B5 示例：(用户输入, 期望输出, 场景说明或 None)。
B5_FEWSHOT_EXAMPLES: tuple[tuple[str, dict[str, Any], str | None], ...] = (
    (
        "就这个吧，确认",
        {"action_type": "CONFIRM_GUIDE", "payload": None},
        None,
    ),
    (
        "把预算改成八千",
        {
            "action_type": "MODIFY_GUIDE",
            "payload": {
                "change_type": "CHANGE_BUDGET",
                "scope_hint": "WHOLE_GUIDE",
                "date": None,
                "target_node_ids": [],
            },
        },
        "已有攻略时说「改预算」是修改，不是重新提需求。",
    ),
    (
        "第二天那个博物馆不想去，去掉",
        {
            "action_type": "MODIFY_GUIDE",
            "payload": {
                "change_type": "REMOVE_NODE",
                "scope_hint": "NODE",
                "date": None,
                "target_node_ids": ["node_002"],
            },
        },
        "已知节点 node_001=古城、node_002=博物馆；节点 ID 从已知清单里选。",
    ),
)


def _json_block(payload: Mapping[str, Any]) -> str:
    """把示例输出渲染成紧凑 JSON 文本（None → null，True → true）。"""

    return json.dumps(payload, ensure_ascii=False, indent=2)


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

    examples_text = "\n\n".join(
        f"示例 {index}：\n用户说：{user}\n输出：\n{_json_block(output)}\n（{note}）"
        for index, (user, output, note) in enumerate(B2_FEWSHOT_EXAMPLES, start=1)
    )

    return f"""你是旅行需求解析器。你的唯一任务：把用户这一轮说的话，填进下面给定的 JSON 结构。

【三条铁律】
1. 只使用用户**明确说过**的信息。用户没说的字段一律留空（null 或 []），
   缺信息由系统的追问流程去补。
2. 你只负责理解需求。开放时间、门票价格、交通路线、住宿、餐厅、天气
   一律交给数据层 —— 这个结构里也没有对应的字段。
3. 目的地只从下方清单里选。用户提到的目的地不在清单里时，
   destination_requests 保持空数组 —— 编造的 ID 或城市名会让下游查无此地。

【填写规则】
- 今天是 {reference_date.isoformat()}。用户说「10月2号」这类没有年份的日期时，
  取最近一次不早于今天的该月日。
- 用户随口提的偏好（例如「不想早起」「最好别太累」）按普通偏好填写字段，
  系统会自动记成可放宽的 SOFT 约束，强度由系统判断。
- `interests` 与 `avoidances` 只写下面的**规范标签**（下游按标签匹配资源，
  写「美食」而不是 `FOOD` 会匹配不到）：

  兴趣：{", ".join(_INTEREST_TAGS)}
  避讳：{", ".join(_AVOIDANCE_TAGS)}

  用户的偏好确实不属于上面标签时，用简短的大写英文标签。
- `mobility_constraints` / `dietary_constraints` / `lodging_preferences` /
  `transport_preferences` 用简短中文短语原样记录用户的意思（例如「老人走不动太多路」）。
- 用户推翻之前的说法时，以**这一轮**为准；这一轮没提到的字段保持原样。
- 只输出**单个 JSON 对象**本身：不写解释文字，不加 markdown 代码块。

【示例】
{examples_text}

【已知目的地清单（名称 → ID）】
{destinations_text}

【当前已收集到的画像（可能为空对象）】
{previous_text}

【必须输出的 JSON 结构（Pydantic JSON Schema）】
{schema}

以下字段由系统填写，你的输出里不出现它们：{", ".join(_DRAFT_SYSTEM_FIELDS)}"""


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
        "请只修正结构问题，保持用户没说过的信息不出现，重新输出完整的 JSON 对象。"
    )


# --- B4 目的地比较 -----------------------------------------------------------


def build_recommend_system_prompt() -> str:
    """B4 的 system prompt：只能在候选集合内比较。"""

    fact_words = "、".join(FACT_CLAIM_KEYWORDS[:14])
    example = B4_FEWSHOT_EXAMPLE
    return f"""你是目的地比较器。候选集合已经通过知识库覆盖初筛，你只从这个集合里选。

【三条铁律】
1. destination_id 只取自下方候选集合 —— 集合外的目的地哪怕你觉得更合适也不输出。
2. 推荐理由只写【证据】里出现过的内容；证据之外的表述交给数据层补充。
3. 你不掌握任何真实旅游事实，这些词不出现在你的输出里：{fact_words}
   同样不出现任何具体时刻（如 09:30）或金额（如 120 元）。

【填写规则】
- 证据不足以支撑的候选直接不输出（宁缺毋滥）。
- tradeoffs 写清楚取舍，例如「可核验资料较少」「自然景观占比可能不足」。
  没有取舍就留空数组。
- 按推荐优先级排序输出。
- 只输出**单个 JSON 对象**，形如：
  {{"recommendations":[{{"destination_id":"...","suitable":true,"reason":"...",
    "tradeoffs":["..."],"risk_flags":["..."]}}]}}
- readiness_id / suggested_days / evidence_ids 由系统填写，你的输出里不出现。
- 不写解释文字，不加 markdown 代码块。

【示例】
场景：{example["scenario"]}
输出：
{_json_block(example["output"])}
（{example["note"]}）"""


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

    examples_text = "\n\n".join(
        f"示例 {index}{f'（{note}）' if note else ''}：\n用户说：{user}\n输出：\n{_json_block(output)}"
        for index, (user, output, note) in enumerate(B5_FEWSHOT_EXAMPLES, start=1)
    )

    return f"""你是行程修改意图识别器。把用户这一轮的话翻译成 UserAction。

【action_type 决策清单（先判类型，再填 payload）】
1. 用户接受当前攻略（「就这个」「可以」「确认」）→ CONFIRM_GUIDE，payload 为 null。
2. 用户在候选目的地里做了一个选择（「就选大理」「第一个吧」）
   → SELECT_DESTINATION，payload 为 null。
3. 用户要改动**已经存在**的攻略或方案 —— 改预算、改日期、增删换安排、
   调节奏、换住宿 —— 一律 MODIFY_GUIDE，payload 必填。
   判断信号：句子里带着「改 / 换 / 去掉 / 加上 / 太贵 / 太累 / 推迟 / 提前」
   这类修改词，且**没有**推翻重来、重新挑选目的地的意思。
   已有攻略时说「把预算改成八千」属于这一类，不是重新提需求。
4. 用户报告旅途中突发情况（航班取消、生病、景区临时关闭）→ REPORT_INCIDENT。

【payload.change_type 取值】
{", ".join(_CHANGE_TYPES)}

【payload.scope_hint 取值】
{", ".join(_SCOPE_HINTS)}

【已知节点 ID（target_node_ids 只能从这里选）】
{nodes_text}

【填写规则】
- 「去掉/不想去/取消某个安排」→ REMOVE_NODE；
  「换成/改成别的」→ REPLACE_NODE；
  「加上/想去某个还没排的」→ ADD_FIXED_NODE；
  「太累了/轻松一点/少安排点」→ LOWER_INTENSITY；
  「换日期/推迟/提前」→ CHANGE_DATE，并把新日期填进 payload.date（YYYY-MM-DD）；
  「预算不够/加点预算」→ CHANGE_BUDGET；
  「节奏慢一点/快一点」→ CHANGE_PACE；
  「换个地方住/酒店换掉」→ CHANGE_LODGING。
- target_node_ids 只使用上面清单里的 ID。用户没指明具体节点时留空数组，
  同时把 scope_hint 设为 DAY 或 WHOLE_GUIDE。
- 你只负责理解意图。开放时间、价格、路线、住宿、天气等事实交给数据层。
- 只输出**单个 JSON 对象**本身：不写解释文字，不加 markdown 代码块。

【示例】
{examples_text}

【必须输出的 JSON 结构（Pydantic JSON Schema）】
{schema}

以下字段由系统填写，你的输出里不出现它们：{", ".join(_ACTION_SYSTEM_FIELDS)}"""


def build_action_user_prompt(text: str) -> str:
    return f"用户这一轮说：\n{text}"


__all__ = [
    "B2_FEWSHOT_EXAMPLES",
    "B4_FEWSHOT_EXAMPLE",
    "B5_FEWSHOT_EXAMPLES",
    "PROMPT_VERSION",
    "build_action_system_prompt",
    "build_action_user_prompt",
    "build_profile_repair_prompt",
    "build_profile_system_prompt",
    "build_profile_user_prompt",
    "build_recommend_system_prompt",
    "build_recommend_user_prompt",
]
