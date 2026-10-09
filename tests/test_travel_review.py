"""抵达日与返程日审查回归；并锁住房型餐食文本按真实承运方写法解析。"""
import pytest

from app import foods, schedule, stay_plan, travel_review as tr

D_OUT, D_TOUR, D_RET = '2026-10-09', '2026-10-10', '2026-10-12'


def workspace(arrival='2026-10-09 12:00', departure=D_OUT + ' 06:00',
              return_departure=D_RET + ' 15:00', start=D_TOUR):
    return {'id': 'review', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '洛阳', 'start_date': start, 'days': 3, 'adults': 2},
            'selected_transport': {'id': 'a', 'kind': 'train', 'name': 'G0',
                                   'departure': departure, 'arrival': arrival,
                                   'arrival_station': '洛阳龙门站',
                                   'selection_status': 'confirmed'},
            'selected_return': {'id': 'b', 'kind': 'train', 'name': 'G1',
                                'departure': return_departure, 'arrival': D_RET + ' 20:00',
                                'selection_status': 'confirmed'},
            'catalog': {'s1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟',
                               'location': '112.47,34.55'}},
            'selected_spots': ['s1'], 'meal_choices': {}, 'visit_requests': {},
            'stay_hotels': {}, 'messages': []}


def test_return_day_meals_move_as_late_as_the_window_allows():
    """返程日餐次尽量往后排（吃完就上车），但不超过餐次窗口、不早于默认时刻。

    用户举例：11:00 发车，准备时刻 09:00 落进早餐窗口，早餐应推到窗口内最晚。
    """
    def return_workspace(departure, days=1, arrival=D_TOUR + ' 06:00', return_day=None):
        return_day = return_day or D_TOUR
        return {'requirements': {'city': '洛阳', 'start_date': D_TOUR, 'days': days, 'adults': 2,
                                 'day_start': '09:00', 'day_end': '18:30'},
                'selected_transport': {'id': 'a', 'kind': 'train', 'name': 'G0',
                                       'departure': D_TOUR + ' 04:00',
                                       'arrival': arrival,
                                       'selection_status': 'confirmed'},
                'selected_return': {'id': 'b', 'kind': 'train', 'name': 'G1',
                                    'departure': return_day + ' ' + departure,
                                    'arrival': return_day + ' 23:30', 'selection_status': 'confirmed'},
                'catalog': {}, 'selected_spots': [], 'meal_choices': {}, 'visit_requests': {}}

    # 11:00 发车：准备时刻 09:00 就是早餐窗口上界，早餐贴到最晚（08:15 开饭，09:00 吃完）
    w = return_workspace('11:00')
    assert schedule.return_bounded(w, D_TOUR) is True
    start = schedule.meal_start(w, D_TOUR, 'breakfast', as_late=True)
    window = schedule.meal_window(w, D_TOUR, 'breakfast')
    assert start == window[1] - 45, (start, window)
    assert start > 8 * 60, '应比默认 08:00 更晚'
    assert start >= window[0]
    # 13:00 发车：早餐推到 09:15（窗口上界 10:00 减 45 分钟）
    later = return_workspace('13:00')
    assert schedule.meal_start(later, D_TOUR, 'breakfast', as_late=True) == 9 * 60 + 15
    # 若抵达太晚导致当天早餐窗口本身为空，则不安排（而不是硬塞）
    too_late = return_workspace('11:00', arrival=D_TOUR + ' 10:00')
    assert schedule.meal_window(too_late, D_TOUR, 'breakfast')[1] < schedule.meal_window(too_late, D_TOUR, 'breakfast')[0]
    assert schedule.meal_start(too_late, D_TOUR, 'breakfast', as_late=True) is None

    # 普通游玩日不受影响：多日行程里只有返程日被推后
    w4 = return_workspace('20:00', days=4, return_day='2026-10-13')
    span = ['2026-10-10', '2026-10-11', '2026-10-12', '2026-10-13']
    for day in span[:-1]:
        assert schedule.return_bounded(w4, day) is False, day
        assert schedule.meal_start(w4, day, 'dinner') == 17 * 60, day
    assert schedule.return_bounded(w4, '2026-10-13') is True
    # 普通游玩日的餐次仍在时间轴上
    meals = {(x['date'], x['period']) for x in schedule.build(w4)['entries'] if x['kind'] == 'meal'}
    assert ('2026-10-11', 'dinner') in meals and ('2026-10-12', 'breakfast') in meals, sorted(meals)


def test_return_day_meals_must_finish_two_hours_before_departure():
    """返程日：必须在发车前 2 小时吃完；赶不上的餐次直接不安排，并给出原因。"""
    def return_workspace(departure):
        return {'requirements': {'city': '洛阳', 'start_date': D_TOUR, 'days': 1, 'adults': 2,
                                 'day_start': '09:00', 'day_end': '18:30'},
                'selected_return': {'id': 'b', 'kind': 'train', 'name': 'G1',
                                    'departure': D_TOUR + ' ' + departure,
                                    'arrival': D_TOUR + ' 23:30', 'selection_status': 'confirmed'},
                'catalog': {}, 'selected_spots': [], 'meal_choices': {}, 'visit_requests': {}}

    def arranged(departure, period):
        w = return_workspace(departure)
        return schedule.meal_start(w, D_TOUR, period)

    # 太早发车：三顿都赶不上，直接不安排
    for period in ('breakfast', 'lunch', 'dinner'):
        assert arranged('08:00', period) is None, period
        assert arranged('09:30', period) is None, period
    # 11:00 发车：早餐还来得及，午晚餐赶不上
    assert arranged('11:00', 'breakfast') is not None
    assert arranged('11:00', 'lunch') is None
    assert arranged('11:00', 'dinner') is None
    # 19:00 发车：晚餐窗口被压到 0 分钟，不安排
    assert arranged('19:00', 'dinner') is None
    assert foods.infeasible(return_workspace('19:00'), D_TOUR, 'dinner')
    # 20:00 起发车：晚餐可安排，且必须在 18:00 前吃完
    dinner = arranged('20:00', 'dinner')
    assert dinner is not None
    window = schedule.meal_window(return_workspace('20:00'), D_TOUR, 'dinner')
    assert window[1] <= schedule.minutes('18:00'), window
    # 时间轴上跳过的那一餐不应出现
    entries = [e for e in schedule.build(return_workspace('19:00'))['entries'] if e['kind'] == 'meal']
    assert all(e['period'] != 'dinner' for e in entries), entries


def test_dinner_window_is_not_capped_by_the_activity_day_end():
    """晚餐是当天最后一件事，不该被"活动结束时刻"卡住。

    用户设 day_end=18:30 表示 18:30 结束游览，不是 18:30 必须吃完饭；
    否则晚餐永远只能排在 17:00 附近。
    """
    def meal_workspace(day_end='18:30', extra=None):
        w = {'requirements': {'city': '洛阳', 'start_date': D_TOUR, 'days': 1, 'adults': 2,
                              'day_start': '09:00', 'day_end': day_end},
             'catalog': {}, 'selected_spots': [], 'meal_choices': {}, 'visit_requests': {}}
        if extra:
            w.update(extra)
        return w

    for day_end in ('18:00', '18:30', '21:00'):
        _, end = schedule.meal_window(meal_workspace(day_end), D_TOUR, 'dinner')
        assert end == 21 * 60, (day_end, end)
    # 早餐与午餐仍在活动时段内，继续受 day_end 约束
    lunch_end = schedule.meal_window(meal_workspace('18:30'), D_TOUR, 'lunch')[1]
    assert lunch_end == 15 * 60, lunch_end
    breakfast_end = schedule.meal_window(meal_workspace('18:30'), D_TOUR, 'breakfast')[1]
    assert breakfast_end == 10 * 60, breakfast_end
    # 有晚间活动时也不该被人为压到 21:00 之前
    evening = meal_workspace('18:30', {
        'catalog': {'s1': {'id': 's1', 'kind': 'spot', 'name': '洛邑古城',
                           'visit_suggestion': {'date': D_TOUR, 'period': 'evening'}}},
        'selected_spots': ['s1']})
    assert schedule.meal_window(evening, D_TOUR, 'dinner')[1] == 21 * 60
    # 返程准备仍是硬约束：返程日不能因为放宽晚餐而排到赶车之后
    returning = meal_workspace('18:30', {
        'selected_return': {'id': 'b', 'kind': 'train', 'name': 'G1',
                            'departure': D_TOUR + ' 19:00', 'arrival': D_TOUR + ' 23:00',
                            'selection_status': 'confirmed'}})
    _, end = schedule.meal_window(returning, D_TOUR, 'dinner')
    assert end < 19 * 60, end


def test_room_meal_text_matches_what_the_carrier_actually_returns():
    """实测途牛写「2份早餐」；只提"含餐"的不能算含早。"""
    assert foods.parse_room_meal('2份早餐')[:2] == (True, 2)
    assert foods.parse_room_meal('1份早餐')[:2] == (True, 1)
    assert foods.parse_room_meal('无早餐')[:2] == (False, 0)
    assert foods.parse_room_meal('含双早')[:2] == (True, 2)
    assert foods.parse_room_meal('含餐')[0] is None, '泛指含餐不能当含早'
    assert foods.parse_room_meal('含正餐')[0] is None
    assert foods.parse_room_meal('待确认')[0] is None


def test_pre_tour_arrival_days_are_counted_as_stay_nights():
    """去程早于开始游玩日时，落地当晚同样要住。"""
    w = workspace()
    assert [d.isoformat() for d in tr.pre_tour_days(w)] == [D_OUT]
    nights = stay_plan.nights(w)
    assert D_OUT in nights and D_TOUR in nights, nights


def test_arrival_day_anchors_on_the_arrival_point():
    """提前抵达日的住宿锚点应是抵达车站，而不是景区或市区中心。"""
    w = workspace()
    tr.apply(w)
    anchor, basis = stay_plan.day_closure(w, D_OUT)
    assert anchor['name'] == '洛阳龙门站', (anchor, basis)
    assert '抵达' in basis
    _, tour_basis = stay_plan.day_closure(w, D_TOUR)
    assert tour_basis != basis


def test_arrival_night_has_a_stay_entry_even_before_a_hotel_is_picked():
    """提前抵达日还没选酒店时，时间轴也要有住宿条目（按抵达地点），不能看起来像漏排。"""
    w = workspace()
    w['stay_hotels'] = {}
    entry = stay_plan.hotel_for(w, D_OUT)
    assert entry is not None, '提前抵达日必须有住宿条目'
    assert entry.get('arrival_area') is True
    assert '洛阳龙门站' in entry['name']
    # 已选酒店时以已选为准
    w['catalog']['h1'] = {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店'}
    w['stay_hotels'] = {D_OUT: 'h1'}
    assert stay_plan.hotel_for(w, D_OUT)['name'] == '示例酒店'
    # 普通游玩日没选酒店时不应凭空造一条
    w['stay_hotels'] = {}
    assert stay_plan.hotel_for(w, '2026-10-11') is None


def test_lunch_is_planned_only_when_arrival_is_early_enough():
    """15:00 前抵达才安排午餐，更晚直接跳过并说明原因。"""
    can, minutes = tr.arrival_can_lunch(workspace(arrival='2026-10-09 12:00'))
    assert can is True and minutes == 12 * 60
    can, minutes = tr.arrival_can_lunch(workspace(arrival='2026-10-09 15:30'))
    assert can is False and minutes == 15 * 60 + 30
    notices = ' '.join(tr.review(workspace(arrival='2026-10-09 16:00'))['notices'])
    assert '不安排午餐' in notices and '跳过' in notices


def test_return_before_noon_drops_that_nights_hotel():
    """返程早于中午 12:00：剔除当天住宿并说明；中午之后不触发。"""
    w = workspace(return_departure=D_RET + ' 09:30')
    w['stay_hotels'] = {D_RET: 'h1'}
    assert tr.return_before_noon(w) is True
    notices, dropped = tr.apply(w)
    assert dropped == [D_RET], dropped
    assert D_RET not in (w.get('stay_hotels') or {})
    assert any('早于中午 12:00' in x and '剔除' in x for x in notices), notices

    later = workspace(return_departure=D_RET + ' 15:00')
    later['stay_hotels'] = {D_RET: 'h1'}
    assert tr.return_before_noon(later) is False
    assert tr.apply(later)[1] == []


def test_unconfirmed_transport_does_not_trigger_review():
    """班次还没确认时不做这些调整，避免把推荐班次当成已定行程。"""
    w = workspace(return_departure=D_RET + ' 09:30')
    w['selected_return']['selection_status'] = 'recommended'
    w['selected_transport']['selection_status'] = 'recommended'
    assert tr.return_before_noon(w) is False
    assert tr.pre_tour_days(w) == []
    assert tr.review(w)['notices'] == []


def test_arrival_day_is_planned_by_place_not_by_clock():
    """提前抵达日只给地点不给时刻：说明里必须点明这一点。"""
    notices = ' '.join(tr.review(workspace())['notices'])
    assert '不显示具体时刻' in notices
    assert '抵达地点' in notices or '抵达站点' in notices
