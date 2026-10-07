"""站点坐标对接测试：用数据服务的交通地点候选补上接驳坐标。

对应《成员三任务说明》"协调者负责车站、机场和酒店实体定位；本人负责时间
拼接"，以及成员一《数据与知识服务接入说明》里的
`search_transport_places`（返回候选，`terminal_confirmed=false`）。

本分支的处理原则：
* 只在工作区还没有该方向坐标时查询一次，成功后写回班次记录；
* 同名候选不止一个（不同站场/航站楼）时不挑第一个，交回业务层确认；
* 候选坐标是"地图文本匹配"，只在说明里如实标注，不当作承运方确认的终端；
* 工具失败或没有候选时不把未知当零耗时。
"""
import asyncio, json
import pytest
from app import planning, time_policy


def workspace(station_name='青岛北站', back='2026-10-13 16:00', hub_place=True):
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    w = {'id': 'w', 'owner_id': 'u', 'revision': 1,
         'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': '2026-10-12', 'days': 2,
                          'adults': 1, 'day_start': '09:00', 'day_end': '18:30'},
         'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': dict(cats['h1']),
         'meal_choices': {}, 'visit_requests': {}, 'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1', 'departure': '2026-10-12 06:00',
                                'arrival': '2026-10-12 10:00', 'arrival_station': station_name,
                                'source': {'name': '途牛', 'queried_at': 'x'}},
         'selected_return': {'id': 'b', 'kind': 'flight', 'name': 'MU1', 'departure': back,
                             'arrival': back, 'departure_station': station_name,
                             'source': {'name': '途牛', 'queried_at': 'x'}}}
    if hub_place:
        w['catalog']['hub'] = {'id': 'hub', 'kind': 'station', 'name': station_name,
                               'location': '120.38,36.10', 'location_status': 'verified'}
    return w


DRAFT = {'title': 't', 'days': [{'date': '2026-10-12', 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                {'date': '2026-10-13', 'items': [{'candidate_id': 's2', 'duration': 90}]}],
         'packing': [], 'todos': []}


def run(w, transport_items=None, monkeypatch=None, tmp_path=None, hub_minutes=20):
    calls = []
    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        if name == 'search_transport_places':
            calls.append(dict(args))
            return {'items': transport_items if transport_items is not None else
                    [{'id': 'amap:B0', 'name': args['keywords'], 'location': '120.38,36.10',
                      'endpoint_scope': 'primary', 'match_status': 'candidate',
                      'terminal_confirmed': False, 'source': {'name': '高德', 'queried_at': 'x'}}]}
        dest = str(args.get('destination') or ''); origin = str(args.get('origin') or '')
        minutes = hub_minutes if ('120.38' in dest or '120.38' in origin) else 20
        return {'mode': args.get('mode'), 'available': True, 'status': 'ok', 'minutes': minutes,
                'distance': 9000, 'polylines': []}
    async def model(messages, **kw):
        if '审核助手' in messages[0]['content']:
            return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
        return {'content': json.dumps(DRAFT)}, {}
    monkeypatch.setattr(planning, 'local_tool', tool)
    monkeypatch.setattr(planning, 'llm', model)
    monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
    return asyncio.run(planning.generate(w, lambda _: None)), calls


def test_station_candidate_is_queried_once_and_reused(monkeypatch, tmp_path):
    w = workspace(hub_place=False)
    plan, calls = run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert calls, '缺坐标时必须向数据服务查站点候选'
    # 去程与返程各查一次，且只查一次
    assert len(calls) == 2
    assert {c['keywords'] for c in calls} == {'青岛北站'}
    assert w['selected_transport']['arrival_station_candidate']['location'].startswith('120.38')
    assert w['selected_return']['departure_station_candidate']['location'].startswith('120.38')
    # 坐标进了路线查询：接驳耗时按 20 分钟而不是兜底 120
    entry = plan['time_policy']['return']['2026-10-13']
    assert entry['minutes'] == 20 + time_policy.WAIT_REQUIREMENTS[time_policy.MODE_FLIGHT][0] + time_policy.DEFAULT_CONNECTION_BUFFER_MINUTES


def test_second_generation_does_not_query_again(monkeypatch, tmp_path):
    w = workspace(hub_place=False)
    run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    _, calls = run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert calls == [], '已经查过的站点不能重复消耗额度'
    assert w['selected_transport']['arrival_station_candidate']['location'].startswith('120.38')


def test_ambiguous_station_candidates_are_not_guessed(monkeypatch, tmp_path):
    """同名候选不止一个时不挑第一个：坐标留空并标待确认。"""
    w = workspace(hub_place=False)
    ambiguous = [{'id': 'amap:B0', 'name': '青岛北站', 'location': '120.38,36.10',
                  'endpoint_scope': 'primary', 'match_status': 'candidate', 'terminal_confirmed': False},
                 {'id': 'amap:B1', 'name': '青岛北站（北广场）', 'location': '120.385,36.105',
                  'endpoint_scope': 'access_point', 'match_status': 'candidate', 'terminal_confirmed': False}]
    plan, calls = run(w, transport_items=ambiguous, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert w['selected_transport']['arrival_station_candidate'] is None
    entry = plan['time_policy']['return']['2026-10-13']
    assert entry['status'] == time_policy.STATUS_NEEDS_CHECK
    assert entry['unverified'] and '尚未查询' in entry['unverified'][0]
    assert entry['station']['location_status'] == 'needs_coordinator'
    assert any('未取得可用坐标' in note for note in plan['time_policy']['notes'])


def test_missing_candidate_keeps_unknown_not_zero(monkeypatch, tmp_path):
    w = workspace(hub_place=False)
    plan, calls = run(w, transport_items=[], monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert calls
    entry = plan['time_policy']['return']['2026-10-13']
    assert entry['status'] == time_policy.STATUS_NEEDS_CHECK
    assert entry['minutes'] == time_policy.FALLBACK_PREPARATION_MINUTES, '未知不能按零耗时'
    assert w['selected_return']['departure_station_candidate'] is None


def test_candidate_is_labelled_not_confirmed(monkeypatch, tmp_path):
    """候选坐标只能标成 candidate：不能声称终端已由用户或承运方确认。"""
    w = workspace(hub_place=False)
    plan, _ = run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    entry = plan['time_policy']['return']['2026-10-13']
    assert entry['station']['location_status'] == 'candidate'
    notes = ' '.join(plan['time_policy']['notes'])
    assert '尚未由用户或承运方确认终端' in notes
    assert '地图文本匹配' in notes


def test_existing_catalog_coordinate_is_preferred_over_query(monkeypatch, tmp_path):
    """工作区已有站点坐标时不再查询，直接用于路线。"""
    w = workspace(hub_place=True)
    plan, calls = run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert calls == [], '已有坐标不应再查询站点'
    entry = plan['time_policy']['return']['2026-10-13']
    assert entry['station']['location_status'] == 'verified'
    assert entry['minutes'] == 20 + time_policy.WAIT_REQUIREMENTS[time_policy.MODE_FLIGHT][0] + time_policy.DEFAULT_CONNECTION_BUFFER_MINUTES


def test_airport_name_selects_airport_kind(monkeypatch, tmp_path):
    w = workspace(station_name='青岛胶东国际机场', hub_place=False)
    _, calls = run(w, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert calls and all(c['kind'] == 'airport' for c in calls)
