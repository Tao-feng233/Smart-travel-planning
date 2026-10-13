"""用户填写的往返交通合成与既有结构的兼容性。

要点（见《往返交通改为用户填写-设计文档》）：
* 合成值必须带日期 —— daily_schedule 用 `[:10]` 判断抵达日/返程日
* 站名缺失不编造，只标 station_pending
* 票价未填时为 None，让 fill_budget 自然跳过（不写成零）
* 用户没填时间时不写入，也不清掉已有记录

日期一律相对今天计算，避免测试随时间腐化（与 test_business.py 的惯例一致）。
"""

from datetime import date, timedelta

from app.persistence import storage
from app.travel import requirements as requirements_mod
from app.travel import travel_synthesis

START = (date.today() + timedelta(days=5)).isoformat()      # 开始游玩日
OUTBOUND = (date.today() + timedelta(days=4)).isoformat()   # 出发日在游玩前一天
LAST_PLAY = (date.today() + timedelta(days=7)).isoformat()  # 最后游玩日 = START + 2
DERIVED_RETURN = (date.today() + timedelta(days=8)).isoformat()  # 默认返程日


def workspace(**over):
    w = storage.new_workspace("test-owner")
    w["requirements"] = {"city": "洛阳", "adults": 2}
    w["requirements"].update(over)
    w["catalog"] = {}
    w["selected_spots"] = []
    return w


def test_outbound_arrival_carries_the_date():
    """缺日期会让 daily_schedule 的首尾日判断退化成完整游玩日。"""
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND,
        "arrival_station": "洛阳龙门站",
        "arrival_time": "16:22",
    })
    t = w["selected_transport"]
    assert t["arrival"] == OUTBOUND + " 16:22"
    assert t["arrival"][:10] == OUTBOUND
    assert t["arrival_station"] == "洛阳龙门站"
    assert t["time_basis"] == "precise"
    assert t["source"] == "user_entered"


def test_period_becomes_a_conservative_start_of_window():
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND,
        "arrival_period": "evening",
    })
    assert w["selected_transport"]["arrival"] == OUTBOUND + " 18:00"
    assert w["selected_transport"]["time_basis"] == "period"


def test_no_time_filled_means_no_synthesis():
    """用户没填时刻相关信息时不写入，避免凭空造出交通记录。"""
    w = workspace(start_date=START, days=3)
    assert not w.get("selected_transport")
    assert not w.get("selected_return")


def test_missing_station_is_not_invented():
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND,
        "arrival_period": "afternoon",
    })
    t = w["selected_transport"]
    assert t["arrival_station"] is None
    assert t["station_pending"] is True


def test_ticket_price_is_optional_and_absent_means_none():
    """票价选填；未填时为 None，让 fill_budget 跳过而不是当成 0。"""
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND, "arrival_period": "afternoon"})
    assert w["selected_transport"]["price"] is None

    w2 = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w2, {
        "outbound_date": OUTBOUND, "arrival_period": "afternoon",
        "intercity_ticket_cost": 545})
    assert w2["selected_transport"]["price"] == 545.0


def test_return_without_date_uses_the_derived_day():
    """未填返程日期时，返程记录落在推导出的默认返程日上。"""
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND,
        "arrival_period": "afternoon",
        "return_station": "洛阳龙门站",
        "return_time": "16:08",
    })
    back = w["selected_return"]
    assert back["departure"] == DERIVED_RETURN + " 16:08"
    assert back["departure_station"] == "洛阳龙门站"


def test_changing_dates_rebuilds_instead_of_losing_the_record():
    """日期变化会先清空记录；合成必须在清空之后，否则信息就丢了。"""
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND, "arrival_period": "afternoon"})
    assert w["selected_transport"]["arrival"] == OUTBOUND + " 13:00"

    earlier = (date.today() + timedelta(days=3)).isoformat()
    requirements_mod.update_requirements(w, {"outbound_date": earlier})
    assert w["selected_transport"]["arrival"] == earlier + " 13:00"


def test_return_is_not_synthesized_without_any_date_basis():
    """日期是地基：没有基准日期就不写返程记录，也不猜日期。"""
    w = workspace()
    w["requirements"]["start_date"] = None
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND, "arrival_period": "afternoon"})
    assert w.get("selected_transport") is not None
    assert w.get("selected_return") is None


def test_rejects_unknown_period_value():
    w = workspace(start_date=START, days=3)
    try:
        requirements_mod.update_requirements(w, {"arrival_period": "midnight"})
    except Exception as error:
        assert "时段" in str(error)
    else:
        raise AssertionError("非法时段应当被拒绝")


def test_summary_mentions_the_derived_return_day():
    w = workspace(start_date=START, days=3)
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND,
        "arrival_station": "洛阳龙门站",
        "arrival_period": "afternoon",
    })
    text = travel_synthesis.summary(w["requirements"])
    assert DERIVED_RETURN in text and "未填日期" in text
