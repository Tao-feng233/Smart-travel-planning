"""红线守卫：把模型输出里「听起来对但不合规」的东西挡在契约之外。

三个解析器（B2/B4/B5）共用这些工具。它们都只做**机械可判定**的检查，
不做语义判断 —— 语义层面的「不许编造事实」由提示词约束 + 下面
`find_fact_claims` 的关键词与数字规则共同兜底。

为什么必须有这一层：模型的输出即使通过了 Pydantic 校验，
也可能在**内容**上越界（编造开放时间、编造目的地 ID、把随口偏好
写成 FIXED 约束）。这些必须在下游之前就被拦住，否则红线形同虚设。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: `Constraint.operator` 的合法取值（`CONTRACTS.md` §2.1）
OPERATORS: frozenset[str] = frozenset(
    {"EQ", "NE", "LT", "LTE", "GT", "GTE", "IN", "NOT_IN", "CONTAINS"}
)

#: 兴趣 / 避讳的**规范标签**（与规则式提取器 `_INTEREST_KEYWORDS` 的取值对齐）。
#:
#: 契约里 `TripProfile.interests` 是 `list[str]`，没有枚举约束，
#: 但下游规划（C4）要按标签匹配资源。模型很容易返回"美食""人文"这类中文词，
#: 而规则式实现返回 `FOOD`/`CULTURE`——两套词表混在一个列表里，
#: 下游既匹配不准、又会出现 `['美食', 'FOOD']` 这种同义重复。
#: 这里统一归一到规则式那套标签（它是当前事实上的公共词表）。
_INTEREST_ALIASES: dict[str, str] = {
    "美食": "FOOD", "吃": "FOOD", "餐饮": "FOOD", "小吃": "FOOD", "吃货": "FOOD", "food": "FOOD",
    "人文": "CULTURE", "文化": "CULTURE", "历史": "CULTURE", "博物馆": "CULTURE",
    "古迹": "CULTURE", "古镇": "CULTURE", "culture": "CULTURE",
    "自然": "NATURE", "风景": "NATURE", "自然风光": "NATURE", "山水": "NATURE",
    "户外": "NATURE", "爬山": "NATURE", "徒步": "NATURE", "nature": "NATURE",
    "夜生活": "NIGHTLIFE", "夜景": "NIGHTLIFE", "酒吧": "NIGHTLIFE", "nightlife": "NIGHTLIFE",
    "购物": "SHOPPING", "逛街": "SHOPPING", "商场": "SHOPPING", "shopping": "SHOPPING",
    "亲子": "FAMILY", "带孩子": "FAMILY", "家庭": "FAMILY", "family": "FAMILY",
}

_AVOIDANCE_ALIASES: dict[str, str] = {
    "不想爬山": "HIGH_INTENSITY_HIKING", "不爬山": "HIGH_INTENSITY_HIKING",
    "爬不动": "HIGH_INTENSITY_HIKING", "不想徒步": "HIGH_INTENSITY_HIKING",
    "高强度徒步": "HIGH_INTENSITY_HIKING",
    "不想挤": "CROWDED_PLACES", "人太多": "CROWDED_PLACES", "避开人流": "CROWDED_PLACES",
    "人群拥挤": "CROWDED_PLACES",
}


def normalize_tag_list(raw: object, *, field: str = "interests") -> list[str]:
    """把标签列表归一到规范词表；**不认识的标签原样保留**（不丢信息）。"""

    aliases = _AVOIDANCE_ALIASES if field == "avoidances" else _INTEREST_ALIASES
    result: list[str] = []
    for item in normalize_string_list(raw):
        canonical = aliases.get(item.strip().lower()) or aliases.get(item.strip()) or item.strip()
        if canonical and canonical not in result:
            result.append(canonical)
    return result

#: 模型**不得**自行设定的约束类型：固定事实和可协商硬约束必须由用户授权
NON_MODEL_CONSTRAINT_KINDS: frozenset[str] = frozenset({"FIXED", "NEGOTIABLE_HARD"})

#: 「这是旅游事实」的关键词。理由/文案里出现这些词，说明模型在用记忆补事实。
#: 只用于**拦截**，不用于生成。
FACT_CLAIM_KEYWORDS: tuple[str, ...] = (
    "开放时间",
    "营业时间",
    "门票",
    "票价",
    "车次",
    "航班",
    "余票",
    "班次",
    "预约电话",
    "距机场",
    "公里外",
    "步行",
    "地铁",
    "直达",
    "评分",
    "点评",
    "库存",
    "房型",
    "气温",
    "降雨",
    "天气",
    "闭馆",
    "淡季",
    "旺季",
)

#: 具体时刻（08:30 / 8点半）与金额（120元 / 380 元/人）
_CLOCK_RE = re.compile(r"\d{1,2}\s*[:：]\s*\d{2}|\d{1,2}\s*点半?")
_AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|块|万元|元/人|元/晚)")
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def find_fact_claims(text: str | None) -> list[str]:
    """返回文本里命中的「旅游事实」痕迹；空列表表示没发现。"""

    if not text:
        return []
    hits = [word for word in FACT_CLAIM_KEYWORDS if word in text]
    hits.extend(match.group(0) for match in _CLOCK_RE.finditer(text))
    hits.extend(match.group(0) for match in _AMOUNT_RE.finditer(text))
    # 去重但保持顺序，便于写进诊断信息
    seen: dict[str, None] = {}
    for item in hits:
        seen.setdefault(item, None)
    return list(seen)


def normalize_choice(value: Any, allowed: Iterable[str]) -> str | None:
    """把模型给的枚举值归一化；不在允许集合内返回 None（由调用方决定丢弃）。"""

    if value is None:
        return None
    text = str(value).strip().upper()
    return text if text in set(allowed) else None


def normalize_string_list(
    value: Any, *, max_items: int = 20, max_length: int = 40
) -> list[str]:
    """清理字符串列表：去空白、丢空值、去重、截断过长的元素。"""

    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        if cleaned not in result:
            result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def normalize_hhmm(value: Any) -> str | None:
    """`earliest_day_start` / `latest_day_end` 只接受 `HH:MM`。"""

    if value is None:
        return None
    text = str(value).strip().replace("：", ":")
    return text if _HHMM_RE.match(text) else None


def normalize_money(value: Any) -> dict[str, Any] | None:
    """把模型给的金额整理成 `Money` 的合法形状（`CONTRACTS.md` §1.1）。

    `Money` 规定 `amount` 与 `min_amount`/`max_amount` **互斥且必须有一方**。
    模型常见的三种「差一点」写法在这里被拉回合法形态：

    * 只写了 `min_amount`（用户说「至少 5000」）→ 当作精确值 `amount`；
    * 只写了 `max_amount`（用户说「最多 5000」）→ 当作精确值 `amount`；
    * 区间的上下界写反了 → 自动纠正顺序。

    这不是替用户假设信息：原始数值全部来自模型对用户话的转写，
    这里只做**形状**归一化，不新增、不推断任何金额。
    """

    if not isinstance(value, Mapping):
        return None
    currency = str(value.get("currency") or "CNY").strip().upper() or "CNY"

    amount = _positive_float(value.get("amount"))
    if amount is not None:
        return {"amount": amount, "currency": currency}

    low = _positive_float(value.get("min_amount"))
    high = _positive_float(value.get("max_amount"))
    if low is None and high is None:
        return None
    if low is None:
        return {"amount": high, "currency": currency}
    if high is None:
        return {"amount": low, "currency": currency}
    if low > high:
        low, high = high, low
    return {"min_amount": low, "max_amount": high, "currency": currency}


def clean_constraints(
    raw: Any, *, base: Sequence[Mapping[str, Any]] = ()
) -> tuple[list[dict[str, Any]], list[str]]:
    """整理约束列表，并把模型不得自行设定的类型降级为 `SOFT`。

    `AGENTS.md`：固定事实和未获授权的可协商硬约束不得被自动突破。
    模型只是「转写用户的话」，它没有资格把某条偏好升级成 `FIXED`，
    因此这里一律按 `SOFT` 处理并留下诊断信息。
    """

    diagnostics: list[str] = []
    result: list[dict[str, Any]] = [dict(item) for item in base]

    if raw is None:
        return result, diagnostics

    items = raw if isinstance(raw, (list, tuple)) else [raw]
    for item in items:
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "").strip()
        if not field:
            diagnostics.append("模型给出的约束没有字段名，已丢弃")
            continue
        kind = str(item.get("kind") or "SOFT").strip().upper()
        if kind in NON_MODEL_CONSTRAINT_KINDS:
            diagnostics.append(
                f"模型把约束「{field}」标为 {kind}，已按 SOFT 处理"
                "（固定/可协商硬约束必须由用户明确授权）"
            )
            kind = "SOFT"
        elif kind != "SOFT":
            kind = "SOFT"

        operator = str(item.get("operator") or "CONTAINS").strip().upper()
        if operator not in OPERATORS:
            diagnostics.append(f"模型给出的算子 {operator!r} 不在契约取值集合内，已丢弃该约束")
            continue

        value = item.get("value")
        if value is None or value == "":
            diagnostics.append(f"约束「{field}」没有值，已丢弃")
            continue

        constraint_id = str(item.get("constraint_id") or "").strip() or f"c_llm_{field}"
        entry: dict[str, Any] = {
            "constraint_id": constraint_id,
            "kind": kind,
            "field": field,
            "operator": operator,
            "value": value,
            "priority": _int_or(item.get("priority"), 0),
            "source_text": _optional_str(item.get("source_text")),
        }
        result = [existing for existing in result if existing.get("constraint_id") != constraint_id]
        result.append(entry)

    return result, diagnostics


def _positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "FACT_CLAIM_KEYWORDS",
    "NON_MODEL_CONSTRAINT_KINDS",
    "OPERATORS",
    "clean_constraints",
    "find_fact_claims",
    "normalize_choice",
    "normalize_hhmm",
    "normalize_money",
    "normalize_string_list",
]
