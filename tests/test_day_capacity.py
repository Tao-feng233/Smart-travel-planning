"""当日容量口径测试：重排与提案校验必须与规划阶段同一套容量。

对应《成员三任务说明》第二批"当数据明确不足时给具体冲突，不为了塞入全部
选择压缩至不合理时长"，以及第三批"可以先实现区域分组、最近可行点与有限
顺序比较"。

旧实现的缺陷：proposals.rebalance 用 windows() 上界当可排分钟（最长可到
当天 24:00），既不扣午餐与往返住宿，也不受 day_end 约束，于是会判定"重排
成功"，落到 planning 仍然压缩或跳过景点——从显式失败变成悄悄缺斤少两。
"""
import asyncio, json
import pytest
from app import planning, proposals, schedule, time_policy


def workspace(station='120.38,36.10', back='2026-10-14 16:00', hotel=True):
 cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
         's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
         'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'},
         'hub': {'id': 'hub', 'kind': 'station', 'name': '青岛北站', 'location': station}}
 return {'id': 'w', 'owner_id': 'u', 'revision': 1,
         'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': '2026-10-12', 'days': 3,
                          'adults': 1, 'day_start': '09:00', 'day_end': '18:30'},
         'selected_spots': ['s1', 's2'], 'catalog': cats,
         'hotel': dict(cats['h1']) if hotel else None, 'meal_choices': {}, 'visit_requests': {},
         'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1', 'departure': '2026-10-12 06:00',
                                'arrival': '2026-10-12 10:00', 'arrival_station': '青岛北站'},
         'selected_return': {'id': 'b', 'kind': 'flight', 'name': 'MU1', 'departure': back,
                             'arrival': back, 'departure_station': '青岛北站'}}


def test_capacity_subtracts_meals_transfers_and_day_end():
 """容量不再等于 windows() 上界：必须扣餐次、往返住宿并受每日结束时刻约束。"""
 w = workspace()
 plain = schedule.capacity(w, '2026-10-12')
 low, high = schedule.windows(w, '2026-10-12')
 assert plain['available_minutes'] < high - max(low, 540), '不能把窗口上界当作可排座位分钟'
 assert plain['meals_minutes'] > 0 and plain['transfer_minutes'] == 60
 assert plain['limit'] == schedule.day_end(w, '2026-10-12')
 assert '餐次' in plain['basis'] and '往返住宿' in plain['basis']
 late = schedule.capacity(w, '2026-10-14')
 # 尚未生成计划时按兜底估计 120 分钟；写入 time_policy 后必须改用真实截止时刻
 baseline = late['limit']
 assert baseline == schedule.minutes('14:00')
 w['time_policy'] = {'return': {'2026-10-14': {'minutes': 160, 'transport_id': 'b'}}}
 assert schedule.capacity(w, '2026-10-14')['limit'] == schedule.minutes('13:20')
 assert schedule.windows(w, '2026-10-14')[1] == schedule.minutes('13:20')
 # 班次换了就不能再复用旧口径
 w['selected_return'] = {**w['selected_return'], 'id': 'b2'}
 assert schedule.capacity(w, '2026-10-14')['limit'] == baseline
 assert schedule.return_cutoff_minutes(w, '2026-10-14') == baseline


def test_capacity_without_hotel_does_not_charge_transfers():
 w = workspace(hotel=False)
 assert schedule.capacity(w, '2026-10-12')['transfer_minutes'] == 0


def test_rebalance_never_exceeds_real_capacity():
 """重排结果逐日不得超过真实容量；装不下时必须返回不可行。"""
 w = workspace()
 dates = ['2026-10-12', '2026-10-13', '2026-10-14']
 rooms = {dt: schedule.capacity(w, dt)['available_minutes'] for dt in dates}
 # 能力最小的那天（抵达/返程边界）单独放一个；其余由重排摊到宽裕的日子
 small = min(rooms, key=lambda dt: rooms[dt])
 packed = [{'date': max(rooms, key=lambda dt: rooms[dt]),
            'items': [{'candidate_id': 's' + str(i), 'duration': 100} for i in range(4)]}]
 result = proposals.rebalance(w, packed, {}, dates, dates)
 assert result
 for day in result:
  load = sum(item['duration'] for item in day['items'])
  assert load <= schedule.capacity(w, day['date'])['available_minutes'], (day['date'], load)
 assert sorted(i['candidate_id'] for d in result for i in d['items']) == ['s0', 's1', 's2', 's3']
 assert len(result) > 1, '重排不能把景点继续堆在同一天，也不能丢景点'
 # 三天都装不下的量必须诚实返回不可行，而不是给出错误的可行分配
 too_much = [{'date': dates[0], 'items': [{'candidate_id': 's' + str(i), 'duration': 240} for i in range(4)]}]
 assert sum(240 for _ in range(4)) > sum(rooms.values())
 assert proposals.rebalance(w, too_much, {}, dates, dates) is None


def test_rebalance_refuses_when_pinned_day_overflows():
 """用户指定的日子本身就装不下时，重排必须说不可行，不能硬塞。"""
 w = workspace()
 dates = ['2026-10-12', '2026-10-13', '2026-10-14']
 groups = [{'date': '2026-10-14', 'items': [{'candidate_id': 's1', 'duration': 240},
                                            {'candidate_id': 's2', 'duration': 240}]}]
 pinned = {'s1': {'date': '2026-10-14', 'period': 'any'}, 's2': {'date': '2026-10-14', 'period': 'any'}}
 assert proposals.rebalance(w, groups, pinned, dates, dates) is None


def test_over_capacity_draft_reports_real_capacity(monkeypatch, tmp_path):
 """超容量的草稿：校验反馈要给出真实容量，而不是窗口上界。"""
 w = workspace()
 over = {'title': 't', 'days': [{'date': '2026-10-14', 'items': [{'candidate_id': 's1', 'duration': 240},
                                                                 {'candidate_id': 's2', 'duration': 240}]}],
         'packing': [], 'todos': []}
 payload = {'dates': ['2026-10-12', '2026-10-13', '2026-10-14'],
            'tour_dates': ['2026-10-12', '2026-10-13', '2026-10-14']}
 async def model(messages, **kw):
  return {'content': json.dumps(over)}, {}
 with pytest.raises(planning.DataError) as error:
  asyncio.run(proposals.create(w, [w['catalog']['s1'], w['catalog']['s2']], payload, '',
                               lambda _: None, model, tmp_path))
 assert error.value.context['capacity']['available_minutes'] < 480
 assert '餐次' in error.value.context['capacity']['basis']


def test_plan_no_longer_needs_to_silently_drop_after_rebalance(monkeypatch, tmp_path):
 """容量对齐后：可行草稿全部落位，不会再出现"重排成功但规划仍跳过"。"""
 w = workspace()
 draft = {'title': 't', 'days': [{'date': '2026-10-12', 'items': [{'candidate_id': 's1', 'duration': 180}]},
                                 {'date': '2026-10-13', 'items': [{'candidate_id': 's2', 'duration': 180}]}],
          'packing': [], 'todos': []}
 async def tool(name, args):
  if name == 'retrieve_guides':
   return {'items': []}
  return {'mode': args.get('mode'), 'available': True, 'status': 'ok', 'minutes': 20,
          'distance': 1800, 'polylines': []}
 async def model(messages, **kw):
  if '审核助手' in messages[0]['content']:
   return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
  return {'content': json.dumps(draft)}, {}
 monkeypatch.setattr(planning, 'local_tool', tool)
 monkeypatch.setattr(planning, 'llm', model)
 monkeypatch.setattr(planning, 'RUNTIME', tmp_path)
 plan = asyncio.run(planning.generate(w, lambda _: None))
 assert not [x for x in plan['warnings'] if '未放入当天行程' in x]
 spots = [e['candidate_id'] for d in plan['days'] for e in d['events'] if e['kind'] == 'spot']
 assert sorted(spots) == ['s1', 's2']
