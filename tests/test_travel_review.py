"""去程/返程选定后的安排审查回归（三条规则由用户提出）。"""
import pytest

from app import stay_plan, travel_review as tr

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


def test_outbound_earlier_than_tour_start_adds_those_nights():
    """去程早于开始游玩日时，落地当晚同样要住。"""
    w = workspace()
    assert [d.isoformat() for d in tr.pre_tour_days(w)] == [D_OUT]
    tr.apply(w)
    assert w['arrival_stay_from'] == D_OUT
    nights = stay_plan.nights(w)
    assert nights[0] == D_OUT, nights
    assert D_TOUR in nights


def test_arrival_day_anchors_lodging_and_meals_on_arrival_point():
    """提前抵达日的住宿锚点应是抵达车站，而不是景区或市区中心。"""
    w = workspace()
    tr.apply(w)
    anchor, basis = stay_plan.day_closure(w, D_OUT)
    assert anchor['name'] == '洛阳龙门站', (anchor, basis)
    # 游玩日仍按当天最后活动
    _, tour_basis = stay_plan.day_closure(w, D_TOUR)
    assert tour_basis != basis


def test_lunch_only_when_arrival_is_early_enough():
    """15:00 前抵达才安排午餐，更晚直接跳过。"""
    early = workspace(arrival='2026-10-09 12:00')
    can, minutes = tr.arrival_can_lunch(early)
    assert can is True and minutes == 12 * 60

    afternoon = workspace(arrival='2026-10-09 15:30')
    can, minutes = tr.arrival_can_lunch(afternoon)
    assert can is False and minutes == 15 * 60 + 30

    late = workspace(arrival='2026-10-09 16:00')
    assert tr.arrival_can_lunch(late)[0] is False
    # 不安排午餐时也要明确说明跳过原因
    notices = ' '.join(tr.review(late)['notices'])
    assert '不安排午餐' in notices and '跳过' in notices


def test_return_before_noon_drops_that_nights_hotel():
    """返程早于中午 12:00：剔除当天住宿并提示。"""
    w = workspace(return_departure=D_RET + ' 09:30')
    w['stay_hotels'] = {D_RET: 'h1'}
    assert tr.return_before_noon(w) is True
    notices, dropped = tr.apply(w)
    assert dropped == [D_RET], dropped
    assert D_RET not in (w.get('stay_hotels') or {})
    assert any('早于中午 12:00' in x and '剔除' in x for x in notices), notices
    # 中午之后返程不触发剔除
    later = workspace(return_departure=D_RET + ' 15:00')
    later['stay_hotels'] = {D_RET: 'h1'}
    assert tr.return_before_noon(later) is False
    _, dropped_later = tr.apply(later)
    assert dropped_later == []


def test_arrival_day_is_planned_by_place_not_by_clock():
    """提前抵达日只给地点不给时刻：说明里必须点明这一点。"""
    w = workspace()
    notices = ' '.join(tr.review(w)['notices'])
    assert '不显示具体时刻' in notices
    assert '抵达地点' in notices or '抵达站点' in notices
