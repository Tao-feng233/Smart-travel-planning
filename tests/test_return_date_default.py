"""未填返程日期时的默认口径与住宿晚数（见 往返交通改为用户填写-设计文档.md 3.4）。

已确认口径：**默认返程日 = 最后一个游玩日的次日**
（起算日 D、days=3 → 游玩日 D/D+1/D+2 → 默认返程日 D+3 → 4 晚，含出发日当晚）。

日期一律相对今天计算，避免测试随时间腐化。
"""

from datetime import date, timedelta

from app.persistence import storage
from app.travel import stay_plan

START = date.today() + timedelta(days=5)
OUTBOUND = date.today() + timedelta(days=4)
DERIVED_RETURN = date.today() + timedelta(days=8)   # START + days(3)


def workspace(**requirements):
    w = storage.new_workspace("test-owner")
    w["requirements"] = {
        "city": "洛阳",
        "start_date": START.isoformat(),
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
    w = workspace(outbound_date=OUTBOUND.isoformat())
    value, basis = stay_plan.return_date_bounds(w)
    assert value == DERIVED_RETURN
    assert "推导" in basis


def test_derived_return_date_matches_an_explicit_one():
    """推导结果必须与用户显式填同一天时一致，否则口径就不对。"""
    derived = workspace(outbound_date=OUTBOUND.isoformat())
    explicit = workspace(
        outbound_date=OUTBOUND.isoformat(), return_date=DERIVED_RETURN.isoformat())
    assert stay_plan.return_date_bounds(derived)[0] == \
        stay_plan.return_date_bounds(explicit)[0]
    assert stay_plan.nights(derived) == stay_plan.nights(explicit)


def test_first_night_is_the_outbound_day_even_without_arrival_station_or_clock():
    """出发日在游玩前一天时，那晚照样住；不需要到达站与精确时刻。"""
    w = workspace(outbound_date=OUTBOUND.isoformat())
    nights = stay_plan.nights(w)
    assert nights[0] == OUTBOUND.isoformat()
    assert len(nights) == 4
    assert nights[-1] == (START + timedelta(days=2)).isoformat()


def test_explicit_return_date_still_wins():
    later = (DERIVED_RETURN + timedelta(days=1)).isoformat()
    w = workspace(outbound_date=OUTBOUND.isoformat(), return_date=later)
    value, basis = stay_plan.return_date_bounds(w)
    assert value == DERIVED_RETURN + timedelta(days=1)
    assert basis == "用户明确的返程日期"
    assert stay_plan.nights(w)[-1] == DERIVED_RETURN.isoformat()


def test_without_start_date_there_are_no_nights():
    """start_date 是地基：缺失时排不出住宿，且不应猜一个日期。"""
    w = workspace(outbound_date=OUTBOUND.isoformat())
    w["requirements"].pop("start_date")
    assert stay_plan.return_date_bounds(w)[0] is None
    assert stay_plan.nights(w) == []
