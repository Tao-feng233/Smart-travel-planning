"""用户填写往返交通时刻的解析契约（见 往返交通改为用户填写-设计文档.md）。"""

from datetime import date, datetime

from app.travel import travel_time


def test_precise_clock_wins_over_period():
    r = {
        "outbound_date": "2026-10-10",
        "arrival_time": "16:22",
        "arrival_period": "morning",  # 应被精确时刻覆盖
    }
    value, basis = travel_time.resolve(r, "outbound")
    assert value == datetime(2026, 10, 10, 16, 22)
    assert basis == travel_time.BASIS_PRECISE


def test_period_uses_its_start_and_is_labelled():
    """时段取起点：窗口更窄 = 更保守，且必须标为估算。"""
    for period, hour in (("morning", 9), ("afternoon", 13), ("evening", 18)):
        r = {"outbound_date": "2026-10-10", "arrival_period": period}
        value, basis = travel_time.resolve(r, "outbound")
        assert value == datetime(2026, 10, 10, hour, 0), period
        assert basis == travel_time.BASIS_PERIOD, period


def test_missing_period_falls_back_to_afternoon_not_full_day():
    """留空时回落下午，而不是整天可用；必须标为 unknown 以便提示。"""
    r = {"outbound_date": "2026-10-10"}
    value, basis = travel_time.resolve(r, "outbound")
    assert value == datetime(2026, 10, 10, 13, 0)
    assert basis == travel_time.BASIS_UNKNOWN


def test_without_base_date_the_time_cannot_be_resolved():
    """日期是地基：没有日期就返回 None，绝不猜一个日子。"""
    value, basis = travel_time.resolve({"arrival_time": "16:22"}, "outbound")
    assert value is None
    assert basis == travel_time.BASIS_UNKNOWN


def test_region_date_key_differs_per_direction():
    """去程用 outbound_date、返程用 return_date。"""
    r = {
        "outbound_date": "2026-10-10",
        "return_date": "2026-10-14",
        "return_time": "16:08",
    }
    assert travel_time.resolve(r, "outbound")[0] == datetime(2026, 10, 10, 13, 0)
    assert travel_time.resolve(r, "return")[0] == datetime(2026, 10, 14, 16, 8)


def test_explicit_base_date_overrides_requirements():
    """补填场景：解析时可用外部传入的基准日期（例如默认返程日）。"""
    r = {"return_period": "morning"}
    value, basis = travel_time.resolve(r, "return", base_date="2026-10-14")
    assert value == datetime(2026, 10, 14, 9, 0)
    assert basis == travel_time.BASIS_PERIOD


def test_bad_clock_values_are_ignored_not_crashing():
    for bad in ("", "abc", "25:00", "12:70", "2026-10-10T16:22", "2026-10-10 16:22"):
        r = {"outbound_date": "2026-10-10", "arrival_time": bad}
        value, basis = travel_time.resolve(r, "outbound")
        assert value == datetime(2026, 10, 10, 13, 0), bad
        assert basis == travel_time.BASIS_UNKNOWN, bad


def test_notes_distinguish_the_three_sources_of_missing_time():
    """三种「时刻缺失」的文案必须不同，否则用户会困惑。"""
    precise = {"outbound_date": "2026-10-10", "arrival_time": "16:22"}
    assert travel_time.note_for(precise, "outbound") == ""

    period = {"outbound_date": "2026-10-10", "arrival_period": "evening"}
    text = travel_time.note_for(period, "outbound")
    assert "晚上" in text and "18:00" in text

    unknown = {"outbound_date": "2026-10-10"}
    text = travel_time.note_for(unknown, "outbound")
    assert "未定" in text and "下午" in text

    no_date = {"arrival_period": "evening"}
    text = travel_time.note_for(no_date, "outbound")
    assert "日期尚未填写" in text


def test_default_return_date_is_the_day_after_the_last_play_day():
    """已确认口径：start=10-11、days=3 → 游玩日 10-11~10-13 → 默认返程日 10-14。"""
    value = travel_time.default_return_date(
        {"start_date": "2026-10-11", "days": 3})
    assert value == date(2026, 10, 14)


def test_default_return_date_needs_start_and_positive_days():
    assert travel_time.default_return_date({"days": 3}) is None
    assert travel_time.default_return_date({"start_date": "2026-10-11"}) is None
    assert travel_time.default_return_date(
        {"start_date": "2026-10-11", "days": 0}) is None
    assert travel_time.default_return_date(
        {"start_date": "2026-10-11", "days": "abc"}) is None
