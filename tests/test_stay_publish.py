"""逐晚住宿下发给前端的契约回归。

前端折叠/已选显示依赖 stay_plan.assignments（后端权威推导）。曾经因为编排行里
过时的 hotel_source 被前端直接读取，导致"已选好的一晚"显示成尚未选、折叠也失效。
"""
import asyncio
import copy

import pytest

from app import agent, main, stay_plan, storage

D1, D2, D3 = '2026-10-12', '2026-10-13', '2026-10-14'


def workspace():
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟', 'location': '112.47,34.55'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '第一晚酒店', 'location': '112.44,34.60'},
            'h2': {'id': 'h2', 'kind': 'hotel', 'name': '第二晚酒店', 'location': '112.45,34.62'}}
    return {'id': 'present', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '洛阳', 'start_date': D1, 'days': 3, 'adults': 2},
            'selected_spots': ['s1'], 'catalog': cats, 'hotel': None,
            'meal_choices': {}, 'visit_requests': {}, 'messages': []}


def test_present_publishes_authoritative_per_night_assignments():
    """present() 必须下发 assignments，且以当前选择为准（不读行内过时字段）。"""
    w = workspace()
    stay_plan.assign(w, 'h1', [D1])
    stay_plan.assign(w, 'h2', [D2])
    # 模拟旧版本写下的过时编排行：hotel_source 还是 unset
    w['stay_plan'] = {**stay_plan.plan(w)}
    for row in w['stay_plan']['rows']:
        row['hotel_source'] = 'unset'
        row['hotel_id'] = None
    out = main.present(w)
    assignments = out['stay_plan']['assignments']
    assert assignments[D1] == {'hotel_id': 'h1', 'source': 'explicit'}, assignments
    assert assignments[D2] == {'hotel_id': 'h2', 'source': 'explicit'}, assignments
    assert assignments[D3] == {'hotel_id': None, 'source': 'unset'}, assignments
    # 未选夜晚随之下发，供界面显示与底部汇总
    assert out['stay_plan']['unassigned'] == [D3], out['stay_plan']['unassigned']


def test_present_keeps_already_queried_candidates():
    """下发时要保留已查到的候选：重算编排行会把 candidate_ids 丢掉。"""
    w = workspace()
    w['stay_plan'] = {**stay_plan.plan(w)}
    row = w['stay_plan']['rows'][0]
    row['candidate_ids'] = ['h1', 'h2']
    row['queried_at'] = '2026-10-09T10:00:00+08:00'
    out = main.present(w)
    first = next(r for r in out['stay_plan']['rows'] if r['date'] == D1)
    assert first['candidate_ids'] == ['h1', 'h2'], first
    assert first['queried_at'] == '2026-10-09T10:00:00+08:00', first


def test_selecting_a_hotel_makes_that_night_count_as_picked(monkeypatch):
    """点选某晚酒店后，该晚在下发数据里必须是"已选"，否则界面不会折叠。"""
    w = workspace()
    for hid in ('h1', 'h2'):
        w['catalog'][hid]['provider_id'] = 900000
    async def vendor(service, tool, params):
        return {'data': {'roomTypes': []}, 'source': {'name': '途牛'}}
    async def tool(name, args):
        return {'items': []}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    monkeypatch.setattr(agent, 'local_tool', tool)
    asyncio.run(agent.handle(w, 'select', {'id': 'h2', 'stay_date': D2}, lambda _: None))
    out = main.present(w)
    assignments = out['stay_plan']['assignments']
    assert assignments[D2] == {'hotel_id': 'h2', 'source': 'explicit'}, assignments
    assert D2 not in out['stay_plan']['unassigned']
    assert set(out['stay_plan']['unassigned']) == {D1, D3}
