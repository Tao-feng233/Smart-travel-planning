"""`TripProfileDraft` 与 `finalize_trip_profile` 的契约测试。

对应 `CONTRACTS.md` §2.4 / §2.5，以及 `fixtures/` 下三个方向的用例：

* `fixtures/valid/trip_profile_draft_incomplete.json`     不完整 Draft 合法
* `fixtures/business/draft_finalize_success.json`         Draft 转 Profile 成功
* `fixtures/business/draft_finalize_failure.json`         强行转换失败
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.legacy import (
    Budget,
    IncompleteProfileError,
    TravelerComposition,
    TripProfile,
    TripProfileDraft,
    finalize_trip_profile,
)


def _complete_draft() -> TripProfileDraft:
    return TripProfileDraft(
        session_id="sess_draft",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        traveler_count=2,
        budget=Budget(amount=5000),
        interests=["FOOD", "CULTURE"],
    )


# --- Draft 不完整也合法 ------------------------------------------------------


def test_incomplete_draft_is_valid() -> None:
    draft = TripProfileDraft(session_id="sess_draft", departure_city="上海")
    assert draft.start_date is None
    assert draft.budget is None
    assert draft.compute_missing_fields() == [
        "start_date",
        "end_date",
        "traveler_count",
        "budget",
    ]


def test_draft_still_rejects_self_contradicting_dates() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        TripProfileDraft(
            session_id="s",
            start_date=date(2026, 10, 6),
            end_date=date(2026, 10, 2),
        )


# --- Draft 转 Profile 成功 ---------------------------------------------------


def test_finalize_success_fills_defaults() -> None:
    profile = finalize_trip_profile(_complete_draft())
    assert isinstance(profile, TripProfile)
    assert profile.duration_days == 5
    # 未说明构成时按成人计
    assert profile.traveler_composition == TravelerComposition(adults=2)
    assert profile.budget.amount == 5000


def test_finalize_keeps_user_provided_composition() -> None:
    draft = _complete_draft().model_copy(
        update={"traveler_composition": TravelerComposition(adults=1, children=1)}
    )
    profile = finalize_trip_profile(draft)
    assert profile.traveler_composition.children == 1


def test_finalize_derives_duration_from_dates() -> None:
    draft = _complete_draft().model_copy(
        update={"end_date": date(2026, 10, 3)}
    )
    assert finalize_trip_profile(draft).duration_days == 2


# --- 强行转换失败 ------------------------------------------------------------


def test_finalize_failure_lists_missing_fields() -> None:
    draft = TripProfileDraft(session_id="s", departure_city="上海", traveler_count=2)
    with pytest.raises(IncompleteProfileError) as excinfo:
        finalize_trip_profile(draft)
    assert excinfo.value.missing_fields == ["start_date", "end_date", "budget"]


def test_finalize_failure_on_composition_mismatch() -> None:
    draft = _complete_draft().model_copy(
        update={"traveler_composition": TravelerComposition(adults=3)}
    )
    with pytest.raises(IncompleteProfileError) as excinfo:
        finalize_trip_profile(draft)
    assert excinfo.value.missing_fields == ["traveler_composition"]


def test_incomplete_draft_cannot_be_finalized_silently() -> None:
    """确认没有“悄悄生成一个字段为空的 TripProfile”这条路径。"""

    draft = TripProfileDraft(session_id="s", budget=Budget(amount=1000))
    with pytest.raises(IncompleteProfileError):
        finalize_trip_profile(draft)


# --- 正式 TripProfile 仍然严格 ----------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    ["departure_city", "start_date", "end_date", "traveler_count", "traveler_composition", "budget"],
)
def test_trip_profile_requires_key_fields(missing_field: str) -> None:
    data = _complete_draft()
    payload = finalize_trip_profile(data).model_dump()
    payload[missing_field] = None
    with pytest.raises(ValidationError):
        TripProfile.model_validate(payload)


def test_missing_fields_is_not_part_of_trip_profile() -> None:
    """`missing_fields` 只属于 Draft；正式画像不该再有这个字段。"""

    assert "missing_fields" not in TripProfile.model_fields
    assert "missing_fields" in TripProfileDraft.model_fields
