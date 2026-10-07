"""餐次口径一致性测试：时间轴、预检查与规划必须用同一份餐次规则。

对应《成员三任务说明》验收条件第 5 行："时间轴、选餐、预检查与生成，
同一输入使用统一时间结果，不在前后阶段相互矛盾"。

旧实现的缺陷：
* access.check 用固定 +15 缓冲与 PERIODS 时长；
  planning.meal 用 round_up(15 分钟) 且 relaxed 节奏下改用 10 分钟缓冲，
  于是预检查通过、生成阶段却报"用餐时间超出可用时段"。
* schedule.provisional 的餐次时刻与 meal_window 不是同一条公式。
"""
import asyncio, json
import pytest
from app import access, foods, planning, schedule


def trip(arrival=None, back=None, pace=None, hotel=True):
 req = {'city': '青岛', 'start_date': '2026-10-12', 'days': 1, 'adults': 1,
        'day_start': '09:00', 'day_end': '18:30'}
 if pace: req['pace'] = pace
 cats = {'f1': {'id': 'f1', 'kind': 'food', 'name': '午餐店', 'location': '120.32,36.05'},
         'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
 return {'requirements': req, 'catalog': cats, 'selected_spots': [],
         'hotel': dict(cats['h1']) if hotel else None,
         'meal_choices': {}, 'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': {'id': 'g', 'kind': 'train', 'name': 'G1',
                                'departure': '2026-10-12 06:00', 'arrival': arrival} if arrival else None,
         'selected_return': {'id': 'b', 'kind': 'flight', 'name': 'MU1',
                             'departure': back, 'arrival': back} if back else None}


def route_options(minutes):
 async def options(a, b):
  return [{'mode': 'walking', 'available': True, 'status': 'ok', 'minutes': minutes,
           'distance': 900, 'polylines': []}]
 return options


def test_precheck_and_planning_agree_on_meal_feasibility():
 """预检查与规划阶段必须用同一份餐次占用口径。"""
 from app.schedule import PERIODS
 w = trip(back='2026-10-12 16:00', pace='relaxed')
 check = asyncio.run(access.check(w, w['catalog']['f1'], w['catalog']['h1'],
                                  route_options(30), planning.choose_route,
                                  ('2026-10-12', 'lunch')))
 allocation = planning.meal_allocation(30, {'pace': 'relaxed'})
 duration = PERIODS['lunch'][2]
 # 预检查里用的占用必须与规划一致：通行（含机动）+ 用餐时长
 assert check['minutes_needed'] == allocation['minutes'] + duration
 assert check['minutes_needed'] == 30 + allocation['buffer'] + duration
 low, high = schedule.meal_window(w, '2026-10-12', 'lunch')
 assert check['status'] == ('available' if low + check['minutes_needed'] <= high else 'time_conflict')
 # 紧凑到装不下时，预检查也必须给出冲突而不是放行
 tight = trip(back='2026-10-12 13:00', pace='relaxed')
 blocked = asyncio.run(access.check(tight, tight['catalog']['f1'], tight['catalog']['h1'],
                                    route_options(30), planning.choose_route,
                                    ('2026-10-12', 'lunch')))
 assert blocked['status'] == 'time_conflict'


def test_precheck_uses_same_allocation_as_planning_for_every_pace():
 from app.schedule import PERIODS
 for pace, buffer in (('relaxed', 15), ('balanced', 10), (None, 10)):
  allocation = planning.meal_allocation(25, {'pace': pace} if pace else {})
  assert allocation['buffer'] == buffer, (pace, allocation)
  assert allocation['minutes'] == 25 + buffer
  w = trip(back='2026-10-12 14:00', pace=pace)
  check = asyncio.run(access.check(w, w['catalog']['f1'], w['catalog']['h1'],
                                   route_options(25), planning.choose_route,
                                   ('2026-10-12', 'lunch')))
  assert check['minutes_needed'] == allocation['minutes'] + PERIODS['lunch'][2]


def test_provisional_meal_time_is_inside_the_same_window():
 """时间轴展示的餐次时刻必须落在 meal_window 内。"""
 w = trip(arrival='2026-10-12 11:00')
 rows = schedule.provisional(w)
 for row in rows:
  if row['kind'] != 'meal': continue
  low, high = schedule.meal_window(w, row['date'], row['period'])
  assert low <= schedule.minutes(row['time']), (row['period'], row['time'], low, high)
  assert schedule.minutes(row['end']) <= max(high, schedule.minutes(row['time'])) + 1, (row['period'], row['end'], high)


def test_meal_choice_rejected_by_precheck_is_rejected_by_planning():
 """预检查拒绝的餐次，规划阶段也必须有同样结论（不能一边放行一边报错）。"""
 w = trip(back='2026-10-12 13:00')
 with pytest.raises(planning.DataError):
  foods.select_meal(w, {'meal_date': '2026-10-12', 'meal_period': 'lunch', 'food_id': 'f1'})
