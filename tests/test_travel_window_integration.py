"""端到端：用户填写的时刻如何影响规划窗口与住宿晚数。

这条链路是整件事的重点 —— 填了时刻，窗口必须收窄；
没填时刻（状态③）必须按下午保守处理并带提示，**不能整天可用**。
"""

from datetime import date, timedelta

from app.persistence import storage
from app.planning import schedule
from app.travel import requirements as requirements_mod
from app.travel import stay_plan

START = date.today() + timedelta(days=5)
OUTBOUND = date.today() + timedelta(days=4)
RETURN = START + timedelta(days=3)          # 最后游玩日 + 1
LAST_PLAY = START + timedelta(days=2)


def workspace():
    w = storage.new_workspace("test-owner")
    w["requirements"] = {
        "city": "洛阳",
        "start_date": START.isoformat(),
        "days": 3,
        "adults": 2,
        "day_start": "09:00",
        "day_end": "18:30",
    }
    w["catalog"] = {}
    w["selected_spots"] = []
    return w


def minutes(clock):
    hour, minute = clock.split(":")
    return int(hour) * 60 + int(minute)


def test_precise_arrival_narrows_the_first_day_window():
    w = workspace()
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND.isoformat(),
        "arrival_station": "洛阳龙门站",
        "arrival_time": "16:22",
        "return_date": RETURN.isoformat(),
        "return_time": "16:08",
        "return_station": "洛阳龙门站",
    })
    start, end = schedule.windows(w, OUTBOUND.isoformat())
    # 抵达日窗口必须从抵达时刻之后开始，而不是 0 点（整天可用）
    assert start > 16 * 60
    assert start < 24 * 60
    back_start, back_end = schedule.windows(w, RETURN.isoformat())
    # 返程日窗口必须在发车时刻之前结束
    assert back_end < minutes("16:08")


def test_period_only_still_narrows_the_window():
    """只填"下午到"也要收窄 —— 取时段起点作为保守值。"""
    w = workspace()
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND.isoformat(),
        "arrival_period": "afternoon",
    })
    start, _ = schedule.windows(w, OUTBOUND.isoformat())
    assert start >= 13 * 60


def test_no_synthesized_transport_means_no_window_narrowing():
    """用户什么都没填时保持既有行为（整天可用），不凭空收窄。"""
    w = workspace()
    start, end = schedule.windows(w, OUTBOUND.isoformat())
    assert (start, end) == (0, 1440)


def test_nights_follow_the_users_dates():
    w = workspace()
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND.isoformat(),
        "arrival_period": "afternoon",
    })
    nights = stay_plan.nights(w)
    assert nights[0] == OUTBOUND.isoformat()
    assert nights[-1] == LAST_PLAY.isoformat()
    assert len(nights) == 4
