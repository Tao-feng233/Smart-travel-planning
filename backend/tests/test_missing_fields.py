"""关键缺失字段判定策略测试（对象为 v0.4 的 `TripProfileDraft`）。"""

from __future__ import annotations

from datetime import date

from app.schemas import Money, TripProfileDraft
from app.services.missing_fields import build_questions, find_missing_fields


def _draft(**overrides) -> TripProfileDraft:
    base = dict(
        session_id="sess_test",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        traveler_count=2,
        budget=Money(amount=5000),
    )
    base.update(overrides)
    return TripProfileDraft(**base)


def test_complete_draft_has_no_missing_fields() -> None:
    assert find_missing_fields(_draft()) == []


def test_empty_draft_lists_all_critical_fields() -> None:
    missing = find_missing_fields(TripProfileDraft(session_id="sess_test"))
    assert missing == [
        "departure_city",
        "start_date",
        "end_date",
        "traveler_count",
        "budget",
    ]


def test_none_draft_treated_as_all_missing() -> None:
    assert find_missing_fields(None) == find_missing_fields(
        TripProfileDraft(session_id="sess_test")
    )


def test_partial_draft_only_reports_missing_parts() -> None:
    draft = _draft(departure_city=None, budget=None)
    assert find_missing_fields(draft) == ["departure_city", "budget"]


def test_soft_preferences_are_not_asked() -> None:
    """兴趣偏好属于软偏好，不阻塞推荐，不应进入追问列表。"""

    draft = _draft(interests=[], pace=None)
    assert find_missing_fields(draft) == []


def test_questions_are_human_readable_and_ordered() -> None:
    questions = build_questions(["departure_city", "budget"])
    assert len(questions) == 2
    assert all("？" in question for question in questions)
    assert "出发" in questions[0]
    assert "预算" in questions[1]


def test_unknown_missing_field_name_is_ignored() -> None:
    assert build_questions(["not_a_field"]) == []


def test_draft_missing_fields_are_computed_not_declared() -> None:
    """Draft 的 missing_fields 由系统计算，忽略外部随意填写的内容。"""

    draft = TripProfileDraft(session_id="s", missing_fields=["随便写的"])
    assert draft.compute_missing_fields() == [
        "departure_city",
        "start_date",
        "end_date",
        "traveler_count",
        "budget",
    ]
