"""关键缺失字段判定策略测试。"""

from __future__ import annotations

from datetime import date

from app.schemas import Budget, TripProfile
from app.services.missing_fields import build_questions, find_missing_fields


def _profile(**overrides) -> TripProfile:
    base = dict(
        session_id="sess_test",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        traveler_count=2,
        budget=Budget(amount=5000),
    )
    base.update(overrides)
    return TripProfile(**base)


def test_complete_profile_has_no_missing_fields() -> None:
    assert find_missing_fields(_profile()) == []


def test_empty_profile_lists_all_critical_fields() -> None:
    missing = find_missing_fields(TripProfile(session_id="sess_test"))
    assert missing == [
        "departure_city",
        "start_date",
        "end_date",
        "traveler_count",
        "budget.amount",
    ]


def test_none_profile_treated_as_all_missing() -> None:
    assert find_missing_fields(None) == find_missing_fields(
        TripProfile(session_id="sess_test")
    )


def test_partial_profile_only_reports_missing_parts() -> None:
    profile = _profile(departure_city=None, budget=None)
    assert find_missing_fields(profile) == ["departure_city", "budget.amount"]


def test_soft_preferences_are_not_asked() -> None:
    """兴趣偏好属于软偏好，不阻塞推荐，不应进入追问列表。"""

    profile = _profile(interests=[], soft_preferences=[], pace=None)
    assert find_missing_fields(profile) == []


def test_questions_are_human_readable_and_ordered() -> None:
    questions = build_questions(["departure_city", "budget.amount"])
    assert len(questions) == 2
    assert all("？" in question for question in questions)
    assert "出发" in questions[0]
    assert "预算" in questions[1]


def test_unknown_missing_field_name_is_ignored() -> None:
    assert build_questions(["not_a_field"]) == []
