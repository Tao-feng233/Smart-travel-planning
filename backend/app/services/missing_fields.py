"""影响规划的缺失字段判定策略。

`TEAM_PROJECT_PLAN.md` 的 B3 要求“缺日期/预算等会继续询问”。
这里定义 C/B 共用的判定口径：哪些字段缺失时**必须**追问，
哪些可以先不追问（例如兴趣偏好，可以边推荐边补）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import TripProfile


@dataclass(frozen=True)
class CriticalField:
    """一个缺失后必须追问的字段。"""

    name: str
    label: str
    question: str


#: 缺失后无法继续推荐/规划的字段。顺序即提问顺序。
CRITICAL_FIELDS: tuple[CriticalField, ...] = (
    CriticalField(
        name="departure_city",
        label="出发地",
        question="你从哪个城市出发？",
    ),
    CriticalField(
        name="start_date",
        label="出发日期",
        question="大概哪天出发？（例如：10月2号）",
    ),
    CriticalField(
        name="end_date",
        label="返回日期",
        question="哪天回来？（例如：10月6号；也可以直接说玩几天）",
    ),
    CriticalField(
        name="traveler_count",
        label="出行人数",
        question="几个人一起去？",
    ),
    CriticalField(
        name="budget.amount",
        label="总预算",
        question="这趟旅行总预算大概多少？（例如：5000 元）",
    ),
)

_BY_NAME = {field.name: field for field in CRITICAL_FIELDS}


def find_missing_fields(profile: TripProfile | None) -> list[str]:
    """返回当前仍缺失的关键字段名。"""
    if profile is None:
        return [field.name for field in CRITICAL_FIELDS]

    missing: list[str] = []
    for field in CRITICAL_FIELDS:
        if not _is_filled(profile, field.name):
            missing.append(field.name)

    # 只给了出发日期、没给返回日期时，用天数推算过就不算缺
    if "end_date" in missing and (
        profile.start_date is not None and _duration_days(profile) is not None
    ):
        missing.remove("end_date")
    return missing


def build_questions(missing_fields: list[str]) -> list[str]:
    """把缺失字段翻译成面向用户的追问。"""
    return [
        _BY_NAME[name].question for name in missing_fields if name in _BY_NAME
    ]


def build_labels(missing_fields: list[str]) -> list[str]:
    return [_BY_NAME[name].label for name in missing_fields if name in _BY_NAME]


def _is_filled(profile: TripProfile, name: str) -> bool:
    if name == "budget.amount":
        return profile.budget is not None and profile.budget.amount is not None
    return getattr(profile, name, None) is not None


def _duration_days(profile: TripProfile) -> int | None:
    """预留：用户只说了“玩几天”时的推算入口。"""
    return None
