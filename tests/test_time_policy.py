"""统一时间契约测试：抵达可用时刻与返程准备时刻必须随实查路线变化。

对应《成员三任务说明》验收条件第 1、2 行：

* 相同 16:00 返程，末站到车站 20 分钟或 80 分钟 → 活动截止随路线变化；
* 高铁与航班 → 准备依据、待核实状态有区别，不套同一固定值。

旧版本把所有场景都写成"固定提前 120 分钟 / 抵达后 90 分钟"，
这里改为断言业务语义，而不是删除用例。
"""
import asyncio, json
import pytest
from app import planning, time_policy


def workspace(station_location='120.38,36.10', departure='2026-10-13 16:00', kind='flight', name='MU1'):
 return {'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':2,'adults':1,
                         'day_start':'09:00','day_end':'18:30'},
         'catalog':{'s1':{'id':'s1','kind':'spot','name':'栈桥','location':'120.31,36.06'},
                    's2':{'id':'s2','kind':'spot','name':'八大关','location':'120.34,36.05'},
                    'h1':{'id':'h1','kind':'hotel','name':'示例酒店','location':'120.30,36.00'},
                    'hub':{'id':'hub','kind':'station','name':'青岛北站','location':station_location}},
         'selected_spots':['s1','s2'],'hotel':{'id':'h1','kind':'hotel','name':'示例酒店','location':'120.30,36.00'},
         'selected_transport':{'id':'g','kind':'train','name':'G1','departure':'2026-10-12 06:00','arrival':'2026-10-12 10:00',
                               'arrival_station':'青岛北站','source':{'name':'途牛','queried_at':'x'}},
         'selected_return':{'id':'b','kind':kind,'name':name,'departure':departure,'arrival':departure,
                            'departure_station':'青岛北站','source':{'name':'途牛','queried_at':'x'}},
         'meal_choices':{},'visit_requests':{},'messages':[],'trace':[],'warnings':{}}


DRAFT={'title':'t','days':[{'date':'2026-10-12','items':[{'candidate_id':'s1','duration':120}]},
                           {'date':'2026-10-13','items':[{'candidate_id':'s2','duration':120}]}],
       'packing':[],'todos':[]}


def run(w,station_minutes=20,monkeypatch=None,tmp_path=None):
 """站点路段返回指定耗时，其余路段返回固定值；记录每次查询。"""
 calls=[]
 async def tool(name,args):
  if name=='retrieve_guides':return {'items':[]}
  if name=='calculate_route':
   destination=str(args.get('destination') or '')
   origin=str(args.get('origin') or '')
   minutes=station_minutes if ('120.38' in destination or '120.38' in origin) else 20
   calls.append({'origin':origin,'destination':destination,'mode':args.get('mode'),'minutes':minutes})
   return {'mode':args.get('mode'),'available':True,'status':'ok','minutes':minutes,'distance':9000,'polylines':[]}
  return {'items':[]}
 async def model(messages,**kw):
  if '审核助手' in messages[0]['content']:return {'content':json.dumps({'issues':[],'summary':'ok'})},{}
  return {'content':json.dumps(DRAFT)},{}
 monkeypatch.setattr(planning,'local_tool',tool)
 monkeypatch.setattr(planning,'llm',model)
 monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 plan=asyncio.run(planning.generate(w,lambda _:None))
 return plan,calls


def return_day(plan):
 return next(d for d in plan['days'] if d['date']=='2026-10-13')


def start_of(day,kind):
 return next(e['start'] for e in day['events'] if e['kind']==kind)


def test_return_cutoff_follows_queried_route_to_station(monkeypatch,tmp_path):
 """20 分钟与 80 分钟的末站到站路线必须给出不同截止时刻。"""
 near,labels_near=run(workspace(),20,monkeypatch,tmp_path)
 assert any('120.38' in c['destination'] or '120.38' in c['origin'] for c in labels_near),'末站→车站必须进入路线查询'
 far,labels_far=run(workspace(),80,monkeypatch,tmp_path)
 near_start=start_of(return_day(near),'transfer_plan')
 far_start=start_of(return_day(far),'transfer_plan')
 assert near_start!=far_start,'不同接驳耗时不能得到同一截止时刻'
 assert near_start>far_start
 assert near['time_policy']['return']['2026-10-13']['minutes']<far['time_policy']['return']['2026-10-13']['minutes']


def test_flight_and_highspeed_train_have_different_basis():
 flight=time_policy.return_preparation({'kind':'flight','name':'MU1'},25)
 train=time_policy.return_preparation({'kind':'train','name':'G2259'},25)
 assert flight['minutes']!=train['minutes']
 assert '值机' in flight['basis'] and '候车' in train['basis']
 assert '值机' not in train['basis'] and '值机' not in time_policy.return_preparation({'kind':'train','name':'K123'},25)['basis']
 assert flight['basis']!=train['basis']


def test_unknown_route_is_marked_needs_check_not_zero():
 unknown=time_policy.return_preparation({'kind':'train','name':'G2259'},None)
 assert unknown['status']==time_policy.STATUS_NEEDS_CHECK
 assert unknown['unverified'] and '尚未查询' in unknown['unverified'][0]
 assert unknown['minutes']>0,'未知不能当成零耗时'
 # 查到路线但终端未确认：整段仍是估计，不能声称已核实（复核 P5）
 estimated=time_policy.return_preparation({'kind':'train','name':'G2259'},25)
 assert estimated['status']==time_policy.STATUS_NEEDS_CHECK and estimated['minutes']==25+30+20
 assert any('终端' in x for x in estimated['unverified'])
 # 终端已确认：候车/值机仍是估计值，所以仍带待核实项，但不影响分钟数
 confirmed=time_policy.return_preparation({'kind':'train','name':'G2259'},25,endpoint_confirmed=True)
 assert confirmed['minutes']==estimated['minutes']
 assert any('承运方实际要求' in x for x in confirmed['unverified'])
 assert confirmed['status'] in (time_policy.STATUS_ESTIMATED,time_policy.STATUS_VERIFIED)


def test_arrival_ready_uses_queried_route_when_available():
 known=time_policy.arrival_ready({'kind':'train','name':'G1'},35)
 assert known['minutes']==35+time_policy.EXIT_AND_BAGGAGE_MINUTES+time_policy.DEFAULT_CONNECTION_BUFFER_MINUTES
 assert known['status']==time_policy.STATUS_NEEDS_CHECK,'终端未确认时不能声称已核实'
 assert any('估计' in x for x in known['unverified'])
 fallback=time_policy.arrival_ready({'kind':'train','name':'G1'},None)
 assert fallback['status']==time_policy.STATUS_NEEDS_CHECK
 assert fallback['unverified']


def test_plan_publishes_single_time_policy_for_all_stages(monkeypatch,tmp_path):
 plan,_=run(workspace(),30,monkeypatch,tmp_path)
 policy=plan['time_policy']
 assert policy['unit']=='minutes' and policy['timezone']=='Asia/Shanghai'
 assert policy['return']['2026-10-13']['minutes']==30+time_policy.WAIT_REQUIREMENTS[time_policy.MODE_FLIGHT][0]+time_policy.DEFAULT_CONNECTION_BUFFER_MINUTES
 # 站点坐标来自工作区里已核对的实体、路线也查到了；但出站与机动仍是估计值，
 # 所以本轮是 estimated：不能用一段道路耗时声称整套准备要求已核实（复核 P5）。
 assert policy['arrival']['2026-10-12']['status']==time_policy.STATUS_ESTIMATED
 assert any('估计' in x for x in policy['arrival']['2026-10-12']['unverified'])
 assert any('返程准备' in note for note in policy['notes'])


def test_station_without_coordinates_is_not_guessed(monkeypatch,tmp_path):
 plan,calls=run(workspace(station_location=None),20,monkeypatch,tmp_path)
 assert not any('青岛北站' in str(c.get('destination')) for c in calls),'缺坐标不能猜站点位置'
 entry=plan['time_policy']['return']['2026-10-13']
 assert entry['status']==time_policy.STATUS_NEEDS_CHECK
 assert entry['station']['location_status']=='needs_coordinator'


def test_prompt_no_longer_teaches_fixed_preparation(monkeypatch,tmp_path):
 """提示词不能再把 90/120 当成规则：时间口径只由 time_policy 决定。"""
 seen=[]
 async def tool(name,args):
  return {'items':[]} if name=='retrieve_guides' else {'mode':args.get('mode'),'available':True,'status':'ok','minutes':20,'distance':9000,'polylines':[]}
 async def model(messages,**kw):
  if '审核助手' in messages[0]['content']:return {'content':json.dumps({'issues':[],'summary':'ok'})},{}
  seen.append(messages[0]['content'])
  return {'content':json.dumps(DRAFT)},{}
 monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 asyncio.run(planning.generate(workspace(),lambda _:None))
 prompt=seen[0]
 assert '到达后90分钟' not in prompt and '出发前120分钟' not in prompt
 assert '统一计算' in prompt
