"""抵达日与返程日审查回归；并锁住房型餐食文本按真实承运方写法解析。"""
import pytest

from app import foods, stay_plan, travel_review as tr

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
