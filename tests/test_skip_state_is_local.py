"""跳过景点的记录不得写进工作区：否则失败一轮会把内部状态带进存储。

对应《成员三任务说明》"不能静默删除选择"与"旧任务不能覆盖新选择"两条：
跳过必须给出可读原因，但记录只能是本次生成的临时状态。
"""
import asyncio, json
import pytest
from app import planning


def workspace():
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            's3': {'id': 's3', 'kind': 'spot', 'name': '啤酒博物馆', 'location': '120.35,36.07'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    return {'id': 'w', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': '2026-10-12', 'days': 2,
                             'adults': 1, 'day_start': '09:00', 'day_end': '17:00'},
            'selected_spots': ['s1', 's2', 's3'], 'catalog': cats, 'hotel': dict(cats['h1']),
            'meal_choices': {}, 'visit_requests': {}, 'messages': [], 'trace': [], 'warnings': {},
            'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1',
                                   'departure': '2026-10-12 06:00', 'arrival': '2026-10-12 06:30'},
            'selected_return': None}


DRAFT = {'title': 't', 'days': [{'date': '2026-10-12', 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                {'date': '2026-10-13', 'items': [{'candidate_id': 's2', 'duration': 120},
                                                                 {'candidate_id': 's3', 'duration': 120}]}],
         'packing': [], 'todos': []}


def install(monkeypatch, tmp_path, route_minutes=150):
    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        return {'mode': args.get('mode'), 'available': True, 'status': 'ok',
                'minutes': route_minutes, 'distance': 5000, 'polylines': []}
    async def model(messages, **kw):
        if '审核助手' in messages[0]['content']:
            return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
        return {'content': json.dumps(DRAFT)}, {}
    monkeypatch.setattr(planning, 'local_tool', tool)
    monkeypatch.setattr(planning, 'llm', model)
    monkeypatch.setattr(planning, 'RUNTIME', tmp_path)


def test_skipped_spots_are_reported_but_not_stored(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path)
    w = workspace()
    plan = asyncio.run(planning.generate(w, lambda _: None))
    assert any('未放入当天行程' in x for x in plan['warnings']), '跳过必须点名'
    assert '_day_skips' not in w, '内部状态不能留在工作区'
    assert '_day_skips' not in plan


def test_stale_internal_state_from_an_earlier_failure_is_ignored(monkeypatch, tmp_path):
    """模拟上一轮失败留下的状态：不能混进新一轮的警告。"""
    install(monkeypatch, tmp_path)
    w = workspace()
    w['_day_skips'] = [{'date': '2026-10-13', 'name': '八大关', 'reason': '上一次失败留下的旧条目'}]
    plan = asyncio.run(planning.generate(w, lambda _: None))
    assert not any('上一次失败留下的旧条目' in x for x in plan['warnings'])
    assert '_day_skips' not in w


def test_retry_does_not_duplicate_skip_messages(monkeypatch, tmp_path):
    """generate 的修复重试不能把同一景点的跳过说明记两遍。"""
    install(monkeypatch, tmp_path, route_minutes=600)
    w = workspace()
    plan = asyncio.run(planning.generate(w, lambda _: None))
    skips = [x for x in plan['warnings'] if '未放入当天行程' in x]
    assert len(skips) == len(set(skips)), skips
    assert '_day_skips' not in w
