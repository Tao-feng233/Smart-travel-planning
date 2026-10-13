"""未填返程日期时的默认口径与住宿晚数（见 往返交通改为用户填写-设计文档.md 3.4）。

已确认口径：**默认返程日 = 最后一个游玩日的次日**
（start=10-11、days=3 → 游玩日 10-11~10-13 → 默认返程日 10-14 → 4 晚）。
"""

from datetime import date

from app.persistence import storage
from app.travel import stay_plan


def workspace(**requirements):
    w = storage.new_workspace("test-owner")
    w["requirements"] = {
        "city": "洛阳",
        "start_date": "2026-10-11",
        "days": 3,
        "adults": 2,
        "day_start": "09:00",
        "day_end": "18:30",
    }
    w["requirements"].update(requirements)
    w["catalog"] = {}
    w["selected_spots"] = []
    return w


def test_missing_return_date_is_derived_from_the_last_play_day():
    w = workspace(outbound_date="2026-10-10")
    value, basis = stay_plan.return_date_bounds(w)
    assert value == date(2026, 10, 14)
    assert "推导" in basis


def test_derived_return_date_matches_an_explicit_one():
    """推导结果必须与用户显式填同一天时一致，否则口径就不对。"""
    derived = workspace(outbound_date="2026-10-10")
    explicit = workspace(outbound_date="2026-10-10", return_date="2026-10-14")
    assert stay_plan.return_date_bounds(derived)[0] == \
        stay_plan.return_date_bounds(explicit)[0]
    assert stay_plan.nights(derived) == stay_plan.nights(explicit)


def test_first_night_is_the_outbound_day_even_without_arrival_station_or_clock():
    """出发日在游玩前一天时，那晚照样住；不需要到达站与精确时刻。"""
    w = workspace(outbound_date="2026-10-10")
    nights = stay_plan.nights(w)
    assert nights[0] == "2026-10-10"
    assert nights == ["2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13"]


def test_explicit_return_date_still_wins():
    w = workspace(outbound_date="2026-10-10", return_date="2026-10-15")
    value, basis = stay_plan.return_date_bounds(w)
    assert value == date(2026, 10, 15)
    assert basis == "用户明确的返程日期"
    assert stay_plan.nights(w)[-1] == "2026-10-14"


def test_without_start_date_there_are_no_nights():
    """start_date 是地基：缺失时排不出住宿，且不应猜一个日期。"""
    w = workspace(outbound_date="2026-10-10")
    w["requirements"].pop("start_date")
    assert stay_plan.return_date_bounds(w)[0] is None
    assert stay_plan.nights(w) == []
