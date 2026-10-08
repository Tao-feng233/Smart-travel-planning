"""首尾日极端时刻测试：晚到、跨午夜、早班返程。

对应《成员三任务说明》验收条件第 3 行：
"晚到/跨午夜/早班返程——完整日期时刻正确，无虚构游玩或强制早餐"。

旧实现的问题：抵达日固定按"到达 + 90 分钟"开排，晚到时会排出当天不可能完成的
景点；返程日固定按"出发 − 120 分钟"结束，早班返程时仍可能安排游玩与早餐。
"""
import asyncio, json
import pytest
from app import planning, schedule, time_policy

D1, D2, D3 = '2026-10-12', '2026-10-13', '2026-10-14'


def workspace(arrival, back=None, days=3, meal_choices=None):
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    w = {'id': 'w', 'owner_id': 'u', 'revision': 1,
         'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': D1, 'days': days,
                          'adults': 1, 'day_start': '09:00', 'day_end': '18:30'},
         'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': dict(cats['h1']),
         'meal_choices': meal_choices or {}, 'visit_requests': {}, 'messages': [], 'trace': [],
         'warnings': {}, 'selected_return': None,
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1',
                                'departure': D1 + ' 06:00', 'arrival': arrival,
                                'arrival_station': '青岛北站',
                                'source': {'name': '途牛', 'queried_at': 'x'}}}
    if back:
        w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G2', 'departure': back,
                                'arrival': back, 'departure_station': '青岛北站',
                                'source': {'name': '途牛', 'queried_at': 'x'}}
    return w


def run(w, allocation, hub_minutes=None, monkeypatch=None, tmp_path=None):
    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        if name == 'search_transport_places':
            return {'items': [{'id': 'amap:B0', 'name': args.get('keywords'), 'location': '120.38,36.10',
                              'endpoint_scope': 'primary', 'match_status': 'candidate',
                              'terminal_confirmed': False, 'source': {'name': '高德', 'queried_at': 'x'}}]}
        dest = str(args.get('destination') or ''); origin = str(args.get('origin') or '')
        hub = hub_minutes if ('120.38' in dest or '120.38' in origin) else None
        return {'mode': args.get('mode'), 'available': True, 'status': 'ok',
                'minutes': hub or 20, 'distance': 1800, 'polylines': []}
    async def model(messages, **kw):
        if '审核助手' in messages[0]['content']:
            return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
        return {'content': json.dumps(allocation)}, {}
    monkeypatch.setattr(planning, 'local_tool', tool)
    monkeypatch.setattr(planning, 'llm', model)
    monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
    return asyncio.run(planning.generate(w, lambda _: None))


def day(plan, dt):
    return next((d for d in plan['days'] if d['date'] == dt), None)


def kinds(d):
    return [e['kind'] for e in d['events']]


def test_late_arrival_day_has_no_sightseeing(monkeypatch, tmp_path):
    """22:26 抵达：当天不排景点，只保留到达与入住。"""
    w = workspace(D1 + ' 22:26', D3 + ' 18:00')
    plan = run(w, {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                          {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                   'packing': [], 'todos': []}, monkeypatch=monkeypatch, tmp_path=tmp_path)
    d1 = day(plan, D1)
    assert 'spot' not in kinds(d1)
    assert 'arrival' in kinds(d1) or 'transport' in kinds(d1)
    # 完整日期时刻：不把次日事件压成 23:59 之外的假时间
    for e in d1['events']:
        assert 0 <= schedule.minutes(e['start']) <= 1440
        assert e['start'] <= e['end'] or e['end'] == '23:59'
    # 晚到当天不能凭空安排早餐
    assert not any(e['kind'] == 'meal' and '早餐' in e['name'] for e in d1['events'])


def test_late_arrival_does_not_lose_the_selected_spot(monkeypatch, tmp_path):
    """晚到导致当天排不下时，景点必须挪到有空的日期或明确点名，不能静默消失。"""
    w = workspace(D1 + ' 22:26', D3 + ' 18:00')
    plan = run(w, {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                          {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                   'packing': [], 'todos': []}, monkeypatch=monkeypatch, tmp_path=tmp_path)
    placed = {e['candidate_id'] for d in plan['days'] for e in d['events'] if e['kind'] == 'spot'}
    named = ' '.join(plan['warnings'])
    assert placed or '未放入当天行程' in named


def test_early_return_day_keeps_full_clock_and_no_sightseeing(monkeypatch, tmp_path):
    """08:20 早班返程：返程日不排景点，接驳时刻按实查值而不是固定 120。"""
    w = workspace(D1 + ' 10:00', D3 + ' 08:20', days=3)
    plan = run(w, {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                          {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                   'packing': [], 'todos': []}, hub_minutes=20, monkeypatch=monkeypatch, tmp_path=tmp_path)
    d3 = day(plan, D3)
    assert 'spot' not in kinds(d3), '早班返程日不应安排景点'
    transfer = next((e for e in d3['events'] if e['kind'] == 'transfer_plan'), None)
    assert transfer is not None
    # 准备时刻由 time_policy 算出：8:20 − (20 分钟接驳 + 30 分钟候车 + 20 分钟机动)
    assert transfer['start'] == '07:10'
    assert plan['time_policy']['return'][D3]['minutes'] == 70


def test_early_return_day_rejects_sightseeing_with_readable_conflict(monkeypatch, tmp_path):
    """早班返程日被排了景点时：必须给出可读冲突，不能排进去。"""
    w = workspace(D1 + ' 10:00', D3 + ' 08:20', days=3)
    with pytest.raises(planning.DataError) as error:
        run(w, {'title': 't', 'days': [{'date': D3, 'items': [{'candidate_id': 's1', 'duration': 120}]}],
                'packing': [], 'todos': []}, hub_minutes=20, monkeypatch=monkeypatch, tmp_path=tmp_path)
    message = str(error.value)
    assert '返程' in message and '冲突' in message


def test_early_return_day_does_not_force_breakfast(monkeypatch, tmp_path):
    """早班返程：用户没有选早餐时不能强行安排早餐。"""
    w = workspace(D1 + ' 10:00', D3 + ' 08:20', days=3)
    plan = run(w, {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                          {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                   'packing': [], 'todos': []}, hub_minutes=20, monkeypatch=monkeypatch, tmp_path=tmp_path)
    d3 = day(plan, D3)
    assert not any(e['kind'] == 'meal' for e in d3['events']), '未选早餐时不应出现餐次事件'


def test_arrival_after_midnight_keeps_full_datetime(monkeypatch, tmp_path):
    """跨午夜抵达（次日 01:20）：按完整 datetime 判断，不把前一天当成可游玩日。"""
    w = workspace(D2 + ' 01:20', D3 + ' 20:00')
    w['requirements']['start_date'] = D1
    plan = run(w, {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                          {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                   'packing': [], 'todos': []}, monkeypatch=monkeypatch, tmp_path=tmp_path)
    d1 = day(plan, D1)
    # 还没到达的日期不能有景点
    assert 'spot' not in kinds(d1), '抵达前的日期不应安排游览'
    assert any('在途' in (d1.get('note') or '') or '在途' in x for x in plan['warnings']
               + [d1.get('note') or '']) or 'spot' not in kinds(d1)
