"""规则式 TripProfile 提取器测试（STUB 行为契约）。

这些用例同时是 B 线替换 LLM 实现时的**行为基准**：
提取器只能使用用户说过的话，不能凭空补全。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.request_parser import StubTripProfileParser

REFERENCE = date(2026, 9, 24)
KNOWN = {"成都": "dest_chengdu", "乐山": "dest_leshan"}


def parse(text: str, previous=None, known=None):
    return StubTripProfileParser().parse(
        session_id="sess_test",
        text=text,
        previous=previous,
        reference_date=REFERENCE,
        known_destinations=known if known is not None else KNOWN,
    )


def test_extracts_full_request() -> None:
    profile = parse("从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，轻松一点")
    assert profile.departure_city == "上海"
    assert profile.start_date == date(2026, 10, 2)
    assert profile.end_date == date(2026, 10, 6)
    assert profile.traveler_count == 2
    assert profile.budget is not None and profile.budget.amount == 5000
    assert set(profile.interests) == {"FOOD", "CULTURE"}
    assert profile.pace == "RELAXED"
    assert (profile.end_date - profile.start_date).days + 1 == 5


def test_extracts_dates_from_range_pattern() -> None:
    profile = parse("10月2-6号去成都")
    assert profile.start_date == date(2026, 10, 2)
    assert profile.end_date == date(2026, 10, 6)


def test_duration_only_works_when_start_known() -> None:
    assert parse("10月2号出发，玩5天").end_date == date(2026, 10, 6)
    # 没有出发日期时，只知道“玩几天”不足以推出日期
    assert parse("想玩5天").end_date is None


def test_past_month_rolls_to_next_year() -> None:
    profile = parse("3月5号出发")
    assert profile.start_date == date(2027, 3, 5)


def test_chinese_number_travelers() -> None:
    assert parse("我们俩一起去").traveler_count == 2
    assert parse("一家三口").traveler_count == 3
    assert parse("三个人").traveler_count == 3


def test_budget_with_wan_unit() -> None:
    assert parse("预算1万").budget.amount == 10_000
    assert parse("总共8000元").budget.amount == 8000


def test_date_digits_are_not_mistaken_for_budget() -> None:
    """“10月2号”里的数字不能被当成预算（否则会静默填错金额）。"""

    assert parse("10月2号到10月6号出发").budget is None


def test_unknown_destination_is_not_invented() -> None:
    profile = parse("我想去哈尔滨")
    assert profile.destination_requests == []
    assert profile.destination_mode.value == "UNKNOWN"


def test_known_destination_becomes_fixed_request() -> None:
    profile = parse("想去成都玩")
    assert profile.destination_mode.value == "SINGLE"
    assert [r.destination_id for r in profile.destination_requests] == ["dest_chengdu"]


def test_noise_input_yields_empty_profile() -> None:
    """无关输入不猜测：所有关键字段保持缺失。"""

    profile = parse("随便看看吧")
    assert profile.departure_city is None
    assert profile.start_date is None
    assert profile.budget is None


def test_merges_with_previous_profile_instead_of_overwriting() -> None:
    first = parse("从上海出发，10月2号到10月6号")
    second = parse("2个人，预算5000元", previous=first)
    assert second.departure_city == "上海"
    assert second.start_date == date(2026, 10, 2)
    assert second.traveler_count == 2
    assert second.budget.amount == 5000


def test_mobility_constraints_are_recorded() -> None:
    profile = parse("带老人一起去，腿脚不太方便不能走太多")
    assert any("老人" in item for item in profile.mobility_constraints)
    assert any("行动不便" in item for item in profile.mobility_constraints)


def test_avoidance_and_soft_preference() -> None:
    profile = parse("不想爬山，也不想早起")
    assert "HIGH_INTENSITY_HIKING" in profile.avoidances
    assert "不想早起" in profile.soft_preferences


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("预算大概3000", 3000),
        ("预算5千", 5000),
        ("人均不算，总共12000块", 12000),
    ],
)
def test_budget_variants(text: str, expected: float) -> None:
    assert parse(text).budget.amount == expected
