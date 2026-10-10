"""住宿起点必须跟"去程日/抵达日"提前，而不是只看开始游玩日。

用户反馈：表单里填了去程 10-10（开始游玩 10-11），却不让他选 10 号晚上的住宿。
根因是 nights() 只认 selection_status=='confirmed' 的班次抵达日，
且完全不看 requirements['outbound_date']。
"""
from app import stay_plan


def trip(**req):
    r = {'city': '青岛', 'origin': '郑州', 'start_date': '2026-10-11',
         'end_date': '2026-10-12', 'days': 2, 'adults': 2}
    r.update(req)
    return {'requirements': r, 'catalog': {}, 'selected_spots': [],
            'visit_requests': {}, 'meal_choices': {}, 'messages': [], 'ui': {}}


def test_outbound_date_earlier_than_start_adds_the_prior_night():
    w = trip(outbound_date='2026-10-10', return_date='2026-10-12')
    assert stay_plan.nights(w) == ['2026-10-10', '2026-10-11']


def test_recommended_arrival_still_counts_as_a_night():
    # 已选班次但状态是 recommended：只表示尚未最终确认，不代表当晚不住
    w = trip(return_date='2026-10-12')
    w['selected_transport'] = {'name': 'G976', 'departure': '2026-10-10 15:07',
                               'arrival': '2026-10-10 21:19', 'selection_status': 'recommended'}
    assert stay_plan.nights(w) == ['2026-10-10', '2026-10-11']


def test_confirmed_arrival_also_counts():
    w = trip(return_date='2026-10-12')
    w['selected_transport'] = {'name': 'G976', 'departure': '2026-10-10 15:07',
                               'arrival': '2026-10-10 21:19', 'selection_status': 'confirmed'}
    assert stay_plan.nights(w) == ['2026-10-10', '2026-10-11']


def test_without_outbound_or_transport_nights_start_at_start_date():
    w = trip(return_date='2026-10-12')
    assert stay_plan.nights(w) == ['2026-10-11']


def test_return_day_is_not_a_lodging_night():
    # 返程当天不住，最后一晚是返程前一天
    w = trip(outbound_date='2026-10-10', return_date='2026-10-12')
    assert '2026-10-12' not in stay_plan.nights(w)


def test_earliest_signal_wins_when_both_present():
    # 班次抵达 10-09 早于表单去程 10-10 时，取更早的
    w = trip(outbound_date='2026-10-10', return_date='2026-10-12')
    w['selected_transport'] = {'name': 'X', 'departure': '2026-10-09 08:00',
                               'arrival': '2026-10-09 20:00', 'selection_status': 'recommended'}
    assert stay_plan.nights(w)[0] == '2026-10-09'
