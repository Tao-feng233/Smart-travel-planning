"""影响规划的缺失字段判定策略。

`TEAM_PROJECT_PLAN.md` 的 B3 要求“缺日期/预算等会继续询问”。
判定对象是 `TripProfileDraft`（`CONTRACTS.md` §2.4），
缺哪些字段由 `FINALIZE_REQUIRED_FIELDS` 统一决定，
本模块只负责把字段名翻译成面向用户的追问。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import TripProfileDraft
from app.schemas.draft import FINALIZE_REQUIRED_FIELDS


@dataclass(frozen=True)
class CriticalField:
    """一个缺失后必须追问的字段。"""

    name: str
    label: str
    question: str


#: 字段名 → (中文名, 追问文案)。字段顺序由 `FINALIZE_REQUIRED_FIELDS` 决定。
_TEXT: dict[str, tuple[str, str]] = {
    "departure_city": ("出发地", "你从哪个城市出发？"),
    "start_date": ("出发日期", "大概哪天出发？（例如：10月2号）"),
    "end_date": ("返回日期", "哪天回来？（例如：10月6号；也可以直接说玩几天）"),
    "traveler_count": ("出行人数", "几个人一起去？"),
    "budget": ("总预算", "这趟旅行总预算大概多少？（例如：5000 元）"),
}


#: 缺失后无法继续推荐/规划的字段。顺序即提问顺序。
CRITICAL_FIELDS: tuple[CriticalField, ...] = tuple(
    CriticalField(name, *_TEXT[name]) for name in FINALIZE_REQUIRED_FIELDS
)

_BY_NAME = {field.name: field for field in CRITICAL_FIELDS}


def find_missing_fields(draft: TripProfileDraft | None) -> list[str]:
    """返回当前仍缺失的关键字段名。"""

    if draft is None:
        return list(FINALIZE_REQUIRED_FIELDS)
    return draft.compute_missing_fields()


def build_questions(missing_fields: list[str]) -> list[str]:
    """把缺失字段翻译成面向用户的追问。"""

    return [_BY_NAME[name].question for name in missing_fields if name in _BY_NAME]


def build_labels(missing_fields: list[str]) -> list[str]:
    return [_BY_NAME[name].label for name in missing_fields if name in _BY_NAME]
