"""房型含早逻辑回归：含早时不再推荐早点铺、时间轴写明含早、计划书说明且不重复计费。"""
import asyncio

import pytest

from app import foods, report, schedule

D1, D2 = '2026-10-12', '2026-10-13'


def workspace(meal='含双早', room=True):
    room_data = (None if not room else
                 {'name': '高级双床房', 'quantity': 1, 'price': 300, 'meal': meal,
                  'cancel': '限时取消', 'source': {'name': '途牛', 'queried_at': '2026-10-09T10:00:00+08:00'},
                  'review': {'issues': []}})
    source = {'name': '途牛', 'queried_at': '2026-10-09T10:00:00+08:00'}
    return {'id': 'breakfast', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '洛阳', 'start_date': D1, 'days': 2, 'adults': 2,
                             'day_start': '09:00', 'day_end': '18:30'},
            'catalog': {'s1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟',
                               'location': '112.47,34.55', 'source': source},
                        'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店',
                               'location': '112.44,34.60', 'price': 300, 'source': source}},
            'selected_spots': ['s1'],
            'hotel': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店',
                      'location': '112.44,34.60', 'price': 300, 'source': source},
            'stay_hotels': {D1: 'h1', D2: 'h1'},
            'selected_room': room_data,
            'meal_choices': {}, 'selected_transport': None, 'selected_return': None,
            'messages': []}


def test_meal_text_parsing_is_literal():
    """含早判断只按字面：认不出来算"未说明"，不能当成含早。"""
    assert foods.parse_room_meal('含双早')[:2] == (True, 2)
    assert foods.parse_room_meal('含早餐')[:2] == (True, 1)
    assert foods.parse_room_meal('无早餐')[:2] == (False, 0)
    assert foods.parse_room_meal('不含早')[:2] == (False, 0)
    assert foods.parse_room_meal('')[0] is None
    assert foods.parse_room_meal('待确认')[0] is None


def test_included_breakfast_skips_external_recommendation():
    """含早时不再把早餐当成"待选外部餐厅"，而是明确说明已含。"""
    w = workspace('含双早')
    info = foods.included_meal(w, D1, 'breakfast')
    assert info['included'] is True and info['count'] == 2 and info['hotel'] == 'h1'
    note = foods.meal_note(w, D1, 'breakfast')
    assert '已含' in note and '无需另选' in note
    # 不含早的房型不产生这条说明
    w2 = workspace('无早餐')
    assert foods.meal_note(w2, D1, 'breakfast') == ''
    assert foods.included_meal(w2, D1, 'breakfast')['included'] is False


def test_timeline_marks_included_breakfast_instead_of_pending():
    """时间轴要把含早写成"酒店含早"，而不是"待选择"。"""
    w = workspace('含双早')
    entries = [e for e in schedule.build(w)['entries'] if e['kind'] == 'meal' and e['period'] == 'breakfast']
    assert entries, '应有早餐条目'
    assert all('酒店含早' in e['name'] for e in entries), entries
    assert all(e.get('included_in_room') for e in entries), entries
    assert all(e['confirmed'] for e in entries), '含早不需要用户再决策，应视为已确定'
    # 不含早时仍是待选择
    w2 = workspace('无早餐')
    other = [e for e in schedule.build(w2)['entries'] if e['kind'] == 'meal' and e['period'] == 'breakfast']
    assert other and all('待选择' in e['name'] for e in other), other


def test_plan_report_states_included_breakfast_without_double_counting():
    """计划书要说明含早且不重复计一份早餐费用。"""
    w = workspace('含双早')
    w['travel_timing'] = {'arrival_ready': {'minutes': 90}, 'return_preparation': {'minutes': 120}}
    plan = {'title': '洛阳旅行', 'created': '2026-10-09T10:00:00+08:00', 'summary': '',
            'days': [], 'packing': [], 'todos': [], 'warnings': [],
            'budget': {'hotel_reference': 600.0, 'nights': 2, 'rooms': 1,
                       'selected_room_quote': 300.0,
                       'note': '住宿按所选房型参考价与晚数估算；餐饮、门票与市内交通尚未核实。',
                       'unknown': ['餐饮', '门票', '市内交通']}}
    w['plan'] = plan
    md = report.markdown(w)
    assert '含早' in md, md
    assert '无需另选' in md, md
    # 预算不因为含早而多出一份早餐费用：预算里不应出现单独的早餐金额项
    budget = plan['budget']
    assert 'breakfast' not in {k.lower() for k in budget}, budget
    assert not any('早餐' in str(k) for k in budget), budget
