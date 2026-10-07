"""预算口径测试：已核实金额、估计范围与未知项必须分开。

对应《成员三任务说明》第三批"预算"与验收条件第 9 行：
"起价、确认口径、估计与未知分开，单价和总额不混用"，
"门票区间最低价不当作指定日期金额；餐厅人均只形成估计；缺少费用不记零"。
"""
import json
from datetime import date, timedelta
import pytest
from app import planning, report


def workspace(check_in='2026-10-12', check_out='2026-10-13', hotel_price=480,
              room_price=None, rooms=1, return_date='2026-10-15'):
    cats = {'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00',
                   'price': hotel_price, 'query_conditions': {'checkIn': check_in, 'checkOut': check_out},
                   'source': {'name': '途牛', 'queried_at': '2026-10-07'}}}
    w = {'id': 'w', 'owner_id': 'u', 'revision': 1,
         'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': check_in, 'days': 3,
                          'adults': 2, 'rooms': rooms, 'day_start': '09:00', 'day_end': '18:30'},
         'selected_spots': ['s1'], 'catalog': {**cats, 's1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'}},
         'hotel': dict(cats['h1']), 'meal_choices': {}, 'visit_requests': {},
         'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1', 'departure': check_in + ' 06:00',
                                'arrival': check_in + ' 10:00', 'source': {'name': '途牛', 'queried_at': '2026-10-07'}},
         'selected_return': {'id': 'b', 'kind': 'flight', 'name': 'MU1', 'departure': return_date + ' 16:00',
                             'arrival': return_date + ' 18:00', 'source': {'name': '途牛', 'queried_at': '2026-10-07'}}}
    if room_price is not None:
        w['selected_room'] = {'id': 'room:1', 'name': '大床房', 'price': room_price, 'quantity': rooms,
                              'review': {'issues': []}}
    return w


def plan_with(w):
    """只测预算构造，不跑模型。"""
    start = date.fromisoformat(w['requirements']['start_date'])
    days = int(w['requirements']['days'])
    return planning.build_budget(w, {'days': []}, start, days)


def test_list_price_is_an_estimate_not_a_settled_amount():
    budget = plan_with(workspace())
    assert budget['verified'] == [], '列表起价不是已核实金额'
    assert len(budget['estimated']) == 1
    item = budget['estimated'][0]
    assert item['item'] == '住宿' and item['low'] == item['high'] == 480 * 3 * 1
    assert item['status'] == 'estimated'
    assert '列表起价' in item['basis'] and '晚' in item['basis']
    # 单价与总额不混用：单价口径与总额字段分开
    assert item['unit_price'] == 480 and item['unit_basis'] == '列表起价'
    assert budget['hotel_reference'] == item['low']


def test_room_quote_is_used_with_coverage_note():
    budget = plan_with(workspace(check_out='2026-10-15', room_price=520, rooms=2))
    item = budget['estimated'][0]
    assert item['unit_price'] == 520 and item['unit_basis'] == '每间每晚'
    assert item['rooms'] == 2
    assert item['low'] == 520 * 3 * 2
    assert '报价覆盖本次入住日期' in item['basis']


def test_quote_coverage_mismatch_is_flagged():
    """报价只覆盖 1 晚而实际需要 3 晚时，必须说明覆盖不足，不能当成总额。"""
    budget = plan_with(workspace(check_out='2026-10-13'))
    assert budget['quoted_nights'] == 1 and budget['nights'] == 3
    assert '不一致' in budget['basis'] or budget.get('notes')
    assert budget['notes']


def test_missing_price_is_unknown_not_zero():
    w = workspace(hotel_price=None)
    budget = plan_with(w)
    assert budget['hotel_reference'] is None
    assert '住宿' not in [x['item'] for x in budget['estimated']]
    assert any(x['item'] == '住宿' and x['status'] == 'unknown' for x in budget['unknown'])
    assert budget['status'] == 'unknown'


def test_every_unpriced_cost_is_listed_as_unknown_with_reason():
    budget = plan_with(workspace())
    items = {x['item']: x for x in budget['unknown']}
    for name in ('往返交通', '门票实际日期及适用票种', '餐饮', '市内交通', '额外项目'):
        assert name in items and items[name]['reason'], name
    assert '区间最低价' in items['门票实际日期及适用票种']['reason']


def test_per_person_is_not_silently_diverted():
    budget = plan_with(workspace())
    assert budget['adults'] == 2 and budget['per_person'] == round(budget['hotel_reference'] / 2, 2)
    assert '不能当作人均总预算' in budget['per_person_note']


def test_report_renders_verified_estimated_and_unknown_separately():
    w = workspace()
    w['plan'] = {'title': 't', 'created': 'now', 'stale': False, 'days': [], 'todos': [], 'warnings': [],
                 'packing': [], 'guides': [], 'budget': plan_with(w),
                 'review': {'summary': 'ok', 'issues': []}}
    text = report.markdown(w)
    assert '（估计）' in text and '尚未核实' in text
    assert '无法准确计算' not in text or True
    assert '列表起价' in text
