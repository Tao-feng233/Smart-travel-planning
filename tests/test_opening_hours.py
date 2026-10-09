"""景区开放时间解析与排程约束的检查。"""
from datetime import date

from app import opening_hours as oh


def test_full_day_venue_parses():
    assert oh.parse('周一至周日 00:00-24:00') == (0, 24 * 60, None)


def test_seasonal_ranges_use_union_and_tightest_last_entry():
    # 资料含季节性多时段：取最早开门/最晚关门，并取最严停止入场
    op = ('5月至10月:周二至周日:09:00-17:00(16:30停止入场),'
          '11月至次年4月:09:00-16:30(16:00停止入场法定节假日除外)')
    opens, closes, last = oh.parse(op)
    assert opens == 9 * 60, opens
    assert closes == 17 * 60, closes
    assert last == 16 * 60, last


def test_last_entry_written_after_the_time_is_recognised():
    # 真实资料里两种顺序都出现：时刻在前（16:30停止入场）与词在前（最晚进入16:30）
    assert oh.parse('8:30-18:00,16:00停止售票,网络票停止换票')[2] == 16 * 60
    assert oh.parse('09:00-17:00(16:30停止入场)')[2] == 16 * 60 + 30
    assert oh.parse('09:00-17:00 最晚进入16:30')[2] == 16 * 60 + 30
    # 只写一个时段、没有停止入场字样时，保守地把关门时刻当作最晚进入
    assert oh.parse('09:00-17:00')[2] == 17 * 60


def test_museum_closed_in_the_evening_is_rejected():
    op = '5月至10月:周二至周日:09:00-17:00(16:30停止入场)'
    ok, why, limit = oh.check(op, '青岛市博物馆', 19 * 60 + 30, 180)
    assert not ok and '停止入场' in why or '入场截止' in why
    ok2, _, _ = oh.check(op, '青岛市博物馆', 10 * 60, 60)
    assert ok2


def test_full_day_outdoor_venue_is_capped_before_evening():
    # 标为 24 小时的户外地点，不该被排到深夜
    op = '周一至周日 00:00-24:00'
    ok, why, limit = oh.check(op, '浮山湾', 21 * 60, 60)
    assert not ok
    assert limit == oh.EVENING_LIMIT
    assert oh.check(op, '浮山湾', 15 * 60, 60)[0]


def test_night_venue_is_not_capped():
    op = '周一至周日 00:00-24:00'
    assert oh.allowed_end(op, '啤酒街夜市') == 24 * 60
    assert oh.check(op, '啤酒街夜市', 21 * 60, 60)[0]


def test_unknown_opening_never_blocks():
    ok, why, limit = oh.check(None, '某处', 21 * 60, 60)
    assert ok and limit is None
    assert oh.parse('') == (None, None, None)
    assert oh.parse('请以景区公告为准') == (None, None, None)
