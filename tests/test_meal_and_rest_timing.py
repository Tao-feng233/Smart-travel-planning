"""锁住时间轴里已正确的餐次与午休行为，作为改动前的基线。

这些规则是此前按用户反馈逐条调好的，重构"餐次跟随景点结束"时不能改坏它们。
数值取自当前实现的实测结果（不是估计）。
"""
from app import pacing, schedule

DAY1, DAY2 = '2026-10-12', '2026-10-13'


def trip(**over):
    w = {
        'requirements': {'city': '杭州', 'origin': '郑州', 'start_date': DAY1, 'days': 2,
                         'adults': 2, 'day_start': '09:00', 'day_end': '18:30'},
        'catalog': {}, 'selected_spots': [], 'meal_choices': {},
        'visit_requests': {}, 'stay_hotels': {}, 'messages': [],
        'selected_transport': {'id': 'o', 'kind': 'train', 'name': 'G0',
                               'departure': DAY1 + ' 06:00', 'arrival': DAY1 + ' 10:00',
                               'selection_status': 'confirmed'},
    }
    w.update(over)
    return w


def return_at(departure):
    return {'id': 'r', 'kind': 'train', 'name': 'G1', 'departure': departure,
            'arrival': departure[:10] + ' 23:00', 'selection_status': 'confirmed'}


def meal_names(w, dt):
    return [e['name'] for e in schedule.provisional(w) if e['date'] == dt and e['kind'] == 'meal']


def has_room(w, dt, period):
    low, high = schedule.meal_window(w, dt, period)
    return low + pacing.meal_duration(w, dt, period) <= high


# ---------- 餐次窗口 ----------

def test_meal_windows_are_the_declared_ones():
    assert schedule.MEAL_WINDOWS['breakfast'] == (7 * 60 + 30, 10 * 60)
    assert schedule.MEAL_WINDOWS['lunch'] == (12 * 60, 15 * 60)
    assert schedule.MEAL_WINDOWS['dinner'] == (17 * 60, 21 * 60)


def test_meal_window_never_starts_before_its_declared_begin():
    w = trip()
    for period, (begin, _) in schedule.MEAL_WINDOWS.items():
        low, _high = schedule.meal_window(w, DAY1, period)
        assert low >= begin, (period, low, begin)


# ---------- 默认时刻 ----------

def test_breakfast_and_dinner_keep_default_times_on_a_normal_day():
    w = trip()
    assert schedule.meal_start(w, DAY1, 'breakfast') is None  # 当天 11:30 才可用，早餐已过
    assert schedule.meal_start(w, DAY1, 'lunch') == 12 * 60
    assert schedule.meal_start(w, DAY1, 'dinner') == 17 * 60
    assert pacing.meal_time(w, DAY1, 'lunch') == 12 * 60
    assert pacing.meal_time(w, DAY1, 'dinner') == 17 * 60


# ---------- 返程日 ----------

def test_only_the_last_meal_before_return_is_pushed_late():
    # 20:00 发车：晚餐是"最靠近返程"的一餐，窗口被压到 17:00–18:00
    w = trip(selected_return=return_at(DAY2 + ' 20:00'))
    assert schedule.last_meal_before_return(w, DAY2) == 'dinner'
    assert schedule.meal_start(w, DAY2, 'lunch') == 12 * 60
    assert schedule.meal_start(w, DAY2, 'dinner') == 17 * 60
    assert meal_names(w, DAY2) == ['早餐 · 待选择', '午餐 · 待选择', '晚餐 · 待选择']


def test_early_return_keeps_breakfast_and_drops_later_meals():
    w = trip(selected_return=return_at(DAY2 + ' 11:00'))
    assert schedule.last_meal_before_return(w, DAY2) == 'breakfast'
    assert has_room(w, DAY2, 'breakfast')
    assert not has_room(w, DAY2, 'lunch')
    assert meal_names(w, DAY2) == ['早餐 · 待选择']


def test_no_meal_after_a_midday_departure():
    w = trip(selected_return=return_at(DAY2 + ' 13:00'))
    assert meal_names(w, DAY2) == ['早餐 · 待选择']


def test_no_meal_when_preparation_ends_before_the_breakfast_window():
    # 06:46 发车、准备 120 分钟 → 04:46 前必须离开，早餐窗口尚未开始
    w = trip(selected_return=return_at(DAY2 + ' 06:46'))
    assert meal_names(w, DAY2) == []


def test_no_meal_on_a_day_after_departure():
    w = trip(selected_return=return_at(DAY2 + ' 13:00'))
    assert meal_names(w, '2026-10-14') == []


# ---------- 未生成计划书时的时间轴 ----------

def test_provisional_has_meals_but_no_hotel_rows():
    w = trip()
    kinds = {e['kind'] for e in schedule.provisional(w)}
    assert 'hotel' not in kinds
    assert 'meal' in kinds
