"""逐晚住宿编排在整合分支上的回归：每晚以当天最后一个活动为锚点分别查询。"""
import asyncio
import copy

import pytest

from app import agent, stay_plan, visits

D1, D2, D3 = '2026-10-12', '2026-10-13', '2026-10-14'


def workspace():
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    return {'id': 'stay', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': D1, 'days': 3,
                             'adults': 2, 'day_start': '09:00', 'day_end': '18:30'},
            'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': None,
            'meal_choices': {}, 'visit_requests': {}, 'messages': []}


def install(monkeypatch):
    calls = []
    async def vendor(service, tool, params):
        calls.append(params)
        prices = {D1: 100, D2: 300}
        return {'data': {'hotels': [{'hotelId': 900001, 'hotelName': '候选酒店',
                                     'lowestPrice': prices.get(params.get('checkIn'), 200)}]},
                'source': {'name': '途牛'}}
    async def tool(name, args):
        return {'items': []}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    monkeypatch.setattr(agent, 'local_tool', tool)
    monkeypatch.setattr(agent, 'recommend', lambda *a, **k: asyncio.sleep(0, result='已比较'))
    monkeypatch.setattr(agent, 'hotel_query_budget', lambda: asyncio.sleep(0, result=5))
    return calls


def test_each_night_is_queried_with_its_own_anchor_and_keeps_its_own_quote(monkeypatch):
    """每晚各自查询：带该晚的入住日期与当天收尾地点；同店两晚的报价互不覆盖。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D2, 'period': 'afternoon'}])
    calls = install(monkeypatch)
    answer = asyncio.run(agent.handle(w, 'search_hotels', {'stay_date': D1}, lambda _: None))
    assert len(calls) == 1 and calls[0]['checkIn'] == D1
    assert calls[0]['poiName'] == '栈桥', calls[0]
    calls.clear()
    asyncio.run(agent.handle(w, 'search_hotels', {'stay_date': D2}, lambda _: None))
    assert calls[0]['checkIn'] == D2 and calls[0]['poiName'] == '八大关', calls[0]
    # 两晚各自留下候选，且报价不同（同店不同晚不能互相覆盖）
    rows = {r['date']: r for r in w['stay_plan']['rows']}
    first = w['catalog'][rows[D1]['candidate_ids'][0]]
    second = w['catalog'][rows[D2]['candidate_ids'][0]]
    assert first['id'] != second['id']
    assert first['price'] == 100 and second['price'] == 300
    assert first['query_conditions']['checkIn'] == D1
    assert second['query_conditions']['checkIn'] == D2
    # 补查第二晚不能把第一晚已查到的候选清空
    assert rows[D1]['candidate_ids'], '补查一晚不得清空其它晚'
    assert '逐晚' in answer or '住' in answer


def test_nights_exclude_the_return_day_and_fall_back_to_the_trip_close(monkeypatch):
    """返程当天不计住宿；当天没有活动时锚点退回行程最后一个活动。"""
    w = workspace()
    # 两个景点都排在 D1：D2 当天没有活动，只能退回行程最后一个活动
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D1, 'period': 'afternoon'}])
    w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G1',
                            'departure': D3 + ' 15:00', 'arrival': D3 + ' 20:00',
                            'selection_status': 'confirmed', 'source': {'name': '途牛'}}
    assert stay_plan.nights(w) == [D1, D2]
    rows = stay_plan.plan(w)['rows']
    assert [r['date'] for r in rows] == [D1, D2]
    # D1 有活动：锚点是当天最后一个活动（八大关）
    assert rows[0]['anchor_name'] == '八大关' and rows[0]['anchor_basis'] == '当天最后一个活动'
    # D2 没有活动：退回行程最后一个活动，而不是留空显示"待定"
    assert rows[1]['anchor_name'] == '八大关' and '最后' in rows[1]['anchor_basis']


def test_full_run_queries_only_within_budget_and_marks_skipped(monkeypatch):
    """一次查全程受剩余额度限制，未查的晚次要明确标出，不能静默少查。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    calls = install(monkeypatch)
    monkeypatch.setattr(agent, 'hotel_query_budget', lambda: asyncio.sleep(0, result=1))
    asyncio.run(agent.handle(w, 'search_hotels', {}, lambda _: None))
    assert len(calls) == 1
    assert w['hotel_query']['skipped_nights'], '未查的晚次必须标出'
