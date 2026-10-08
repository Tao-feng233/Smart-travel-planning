"""返程日期口径测试：未确认的返程不能被写成确定条件。

对应《成员三任务说明》第二批"用户未明确返程日期时，不直接固定为游玩结束
次日；向业务层返回待确认建议，由成员二保存来源与确认状态"。

旧实现的缺陷：journey.travel_date() 在 requirements 没有 return_date 时
直接返回 start_date + days（即游玩结束次日），并被返程搜索与展示当作
既定返程日使用。
"""
import asyncio, json
import pytest
from app import journey, planning, time_policy


def workspace(return_departure=None, return_date=None, days=3):
    cats = {'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'},
            's1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'}}
    req = {'city': '青岛', 'origin': '郑州', 'start_date': '2026-10-12', 'days': days,
           'adults': 1, 'day_start': '09:00', 'day_end': '18:30'}
    if return_date: req['return_date'] = return_date
    w = {'id': 'w', 'owner_id': 'u', 'revision': 1, 'requirements': req,
         'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': dict(cats['h1']),
         'meal_choices': {}, 'visit_requests': {}, 'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1',
                                'departure': '2026-10-12 06:00', 'arrival': '2026-10-12 10:00',
                                'arrival_station': '青岛北站'},
         'selected_return': None}
    if return_departure:
        w['selected_return'] = {'id': 'b', 'kind': 'flight', 'name': 'MU1',
                                'departure': return_departure, 'arrival': return_departure,
                                'departure_station': '青岛北站'}
    return w


def draft(*dates):
    return {'title': 't', 'days': [{'date': d, 'items': []} for d in dates], 'packing': [], 'todos': []}


def draft_with_spots():
    """两个景点分别放在前两天；第三天留给返程。"""
    return {'title': 't', 'days': [{'date': '2026-10-12', 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                   {'date': '2026-10-13', 'items': [{'candidate_id': 's2', 'duration': 120}]}],
            'packing': [], 'todos': []}


def test_unconfirmed_return_is_a_suggestion_not_a_fact():
    status = journey.return_date_status(workspace())
    assert status['status'] == 'suggested'
    assert status['date'] == '2026-10-15', '仍可给出建议日期，但必须标明是建议'
    assert '尚未由用户确认' in status['basis']
    assert journey.return_date_confirmed(workspace()) is False


def test_explicit_return_date_or_selected_transport_is_confirmed():
    assert journey.return_date_status(workspace(return_date='2026-10-16'))['status'] == 'confirmed'
    confirmed = journey.return_date_status(workspace(return_departure='2026-10-14 20:00'))
    assert confirmed['status'] == 'confirmed' and confirmed['date'] == '2026-10-14'
    assert journey.return_date_confirmed(workspace(return_departure='2026-10-14 20:00')) is True


def test_plan_says_return_date_is_pending(monkeypatch, tmp_path):
 """没有返程班次时生成计划：必须明确说出返程日期待确认，不当作既定条件。"""
 w = workspace()
 alloc = draft_with_spots()
 async def tool(name, args):
  return {'items': []} if name == 'retrieve_guides' else {
   'mode': args.get('mode'), 'available': True, 'status': 'ok', 'minutes': 20,
   'distance': 1800, 'polylines': []}
 async def model(messages, **kw):
  if '审核助手' in messages[0]['content']:
   return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
  return {'content': json.dumps(alloc)}, {}
 monkeypatch.setattr(planning, 'local_tool', tool)
 monkeypatch.setattr(planning, 'llm', model)
 monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
 plan = asyncio.run(planning.generate(w, lambda _: None))
 assert plan['return_date_status']['status'] == 'suggested'
 assert plan['time_policy']['return_date_status']['status'] == 'suggested'
 assert any('返程日期尚未确认' in x for x in plan['warnings'])
 assert any('返程日期待确认' in note for note in plan['time_policy']['notes'])
 # 只有建议日期时，不得把"提前准备"说成已核实的返程条件
 assert 'return' not in plan['time_policy'] or all(
  entry['status'] != 'verified' for entry in plan['time_policy']['return'].values())


def test_confirmed_return_keeps_verified_cutoff(monkeypatch, tmp_path):
 w = workspace(return_departure='2026-10-14 16:00')
 alloc = draft_with_spots()
 async def tool(name, args):
  return {'items': []} if name == 'retrieve_guides' else {
   'mode': args.get('mode'), 'available': True, 'status': 'ok', 'minutes': 20,
   'distance': 1800, 'polylines': []}
 async def model(messages, **kw):
  if '审核助手' in messages[0]['content']:
   return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
  return {'content': json.dumps(alloc)}, {}
 monkeypatch.setattr(planning, 'local_tool', tool)
 monkeypatch.setattr(planning, 'llm', model)
 monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
 plan = asyncio.run(planning.generate(w, lambda _: None))
 assert plan['time_policy']['return_date_status']['status'] == 'confirmed'
 assert 'return_date_status' not in plan, '只有未确认时才需要额外标注待确认状态'
 assert not any('返程日期尚未确认' in x for x in plan['warnings'])
 for entry in plan['time_policy']['return'].values():
  # 没有站点坐标时仍会因"接驳路线未核实"标待核实，但原因不能是返程日期未确认
  assert all('返程日期尚未确认' not in reason for reason in entry.get('unverified',[]))


def test_confirmed_return_with_station_coordinates_is_verified(monkeypatch, tmp_path):
 """有站点坐标时，确认过的返程日接驳应给出已核实口径。"""
 w = workspace(return_departure='2026-10-14 16:00')
 w['catalog']['hub'] = {'id': 'hub', 'kind': 'station', 'name': '青岛北站',
                        'location': '120.38,36.10', 'location_status': 'verified'}
 alloc = draft_with_spots()
 async def tool(name, args):
  if name == 'retrieve_guides':
   return {'items': []}
  dest = str(args.get('destination') or ''); origin = str(args.get('origin') or '')
  minutes = 20 if ('120.38' in dest or '120.38' in origin) else 15
  return {'mode': args.get('mode'), 'available': True, 'status': 'ok', 'minutes': minutes,
          'distance': 1800, 'polylines': []}
 async def model(messages, **kw):
  if '审核助手' in messages[0]['content']:
   return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
  return {'content': json.dumps(alloc)}, {}
 monkeypatch.setattr(planning, 'local_tool', tool)
 monkeypatch.setattr(planning, 'llm', model)
 monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
 plan = asyncio.run(planning.generate(w, lambda _: None))
 entry = plan['time_policy']['return']['2026-10-14']
 assert entry['status'] == 'verified' and entry['unverified'] == []
 assert entry['station']['location_status'] == 'verified'
 assert entry['minutes'] == 20 + time_policy.WAIT_REQUIREMENTS[time_policy.MODE_FLIGHT][0] + time_policy.DEFAULT_CONNECTION_BUFFER_MINUTES
