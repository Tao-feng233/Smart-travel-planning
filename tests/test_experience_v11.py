import asyncio,json
import pytest
from app import planning

def test_early_return_after_three_tour_days(monkeypatch,tmp_path):
 w={'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':3,'adults':1},'catalog':{},'selected_spots':['a','b','c'],'selected_return':{'name':'G2259','departure':'2026-10-15 08:20','arrival':'2026-10-15 13:20','selection_status':'confirmed'}}
 w['catalog']={i:{'id':i,'name':i,'kind':'spot'} for i in w['selected_spots']}
 async def tool(*args):return {'items':[]}
 async def model(messages,**kw):
  if '独立审核' in messages[0]['content']:return {'content':json.dumps({'issues':[]})},{}
  return {'content':json.dumps({'days':[{'date':f'2026-10-{12+n}','items':[{'candidate_id':i,'duration':60}]} for n,i in enumerate(w['selected_spots'])]})},{}
 monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 p=asyncio.run(planning.generate(w,lambda _:None))
 back=p['days'][-1]
 assert back['date']=='2026-10-15'
 assert [e['kind'] for e in back['events']]==['transfer_plan','transport']
 assert not any('重叠' in x or '返程冲突' in x for x in p['warnings'])


def draft_workspace():
 return {'requirements':{'city':'青岛','start_date':'2026-10-12','days':3},'catalog':{'a':{'id':'a','name':'栈桥','kind':'spot','location':'120.3,36.0'},'b':{'id':'b','name':'崂山','kind':'spot','location':'120.6,36.2'},'h':{'id':'h','name':'酒店','kind':'hotel','location':'120.3,36.01'}},'selected_spots':['a','b'],'hotel':{'id':'h','name':'酒店','kind':'hotel','location':'120.3,36.01'},'selected_return':{'id':'t','name':'G2259','departure':'2026-10-15 08:20','arrival':'2026-10-15 12:20'}}

def test_timeline_meals_respect_arrival_and_return():
 from app import schedule
 w=draft_workspace();w['selected_transport']={'arrival':'2026-10-12 15:00','departure':'2026-10-12 07:08'}
 result=schedule.build(w)
 assert not any(x['kind']=='meal' and x['date']=='2026-10-15' for x in result['entries'])
 assert [x['period'] for x in result['meal_slots'] if x['date']=='2026-10-12']==['dinner']
 assert any(x['kind']=='transport' and x['date']=='2026-10-15' for x in result['entries'])
 assert result['provisional'] and result['conflicts']==[]

def test_fixed_impossible_window_warns_in_either_selection_order():
 from app import schedule
 w=draft_workspace();w['visit_requests']={'b':{'date':'2026-10-14','period':'morning'}}
 assert schedule.conflicts(w)==[]
 w['selected_return']['departure']='2026-10-14 08:20'
 c=schedule.conflicts(w)[0]
 assert c['date']=='2026-10-14' and c['candidate_ids']==['b'] and c['direction']=='return'
 w['selected_return']['departure']='2026-10-15 08:20'
 assert schedule.conflicts(w)==[]

def test_food_reference_uses_current_schedule_not_stale_plan():
 from app import foods
 w=draft_workspace();w['visit_requests']={'b':{'date':'2026-10-13','period':'morning'}}
 w['plan']={'stale':True,'days':[{'date':'2026-10-13','events':[{'kind':'spot','candidate_id':'a','end':'12:00'}]}]}
 assert foods.anchors(w,{'meal_date':'2026-10-13','meal_period':'lunch'})[0]['id']=='b'

def test_visit_order_validation_and_timeline():
 from app import visits,schedule
 w=draft_workspace();visits.save(w,[{'candidate_id':i,'date':'2026-10-12','period':'any'} for i in ['a','b']],['b','a'])
 assert [x['candidate_id'] for x in schedule.build(w)['entries'] if x['kind']=='spot']==['b','a']
 with pytest.raises(planning.DataError):visits.save(w,[],['x'])


def test_actual_return_conflict_keeps_actionable_context(monkeypatch,tmp_path):
 w=draft_workspace();w['requirements']['days']=1;w['requirements']['start_date']='2026-10-14';w['selected_return']['departure']='2026-10-14 10:00';w['selected_spots']=['a'];w.pop('hotel')
 async def tool(*args):return {'items':[]}
 async def model(*args,**kw):return {'content':json.dumps({'days':[{'date':'2026-10-14','items':[{'candidate_id':'a','duration':60}]}]})},{}
 monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 with pytest.raises(planning.DataError) as error:asyncio.run(planning.generate(w,lambda _:None))
 assert error.value.context['date']=='2026-10-14' and error.value.context['candidate_ids']==['a']


def test_self_arranged_meals_are_not_marked_pending():
 from app import schedule
 w=draft_workspace();w['meal_mode']='self'
 assert all(x['confirmed'] and '自行安排' in x['name'] for x in schedule.build(w)['meal_slots'])

def test_model_can_execute_detail_and_date_arguments(monkeypatch):
 from app import agent
 w=draft_workspace();seen=[]
 async def handle(w,action,args,progress):seen.append((action,args));return '已查询'
 async def weather(*args):return
 monkeypatch.setattr(agent,'handle',handle);monkeypatch.setattr(agent,'ensure_weather',weather)
 token=agent.replies.PREFIX.set('');sink=agent.replies.SINK.set(None)
 try:
  asyncio.run(agent.execute({'workspace':w,'text':'查询景点详情','progress':lambda _:None,'intent':{'action':'place_detail','patch':{},'id':'a','view':'spot'}}))
  assert seen[-1][1]['id']=='a' and seen[-1][1]['view']=='spot'
  asyncio.run(agent.execute({'workspace':w,'text':'查询门票','progress':lambda _:None,'intent':{'action':'ticket','patch':{},'id':'a','visit_date':'2026-10-13'}}))
  assert seen[-1][1]['visit_date']=='2026-10-13'
 finally:agent.replies.PREFIX.reset(token);agent.replies.SINK.reset(sink)


def test_actual_route_conflict_repairs_flexible_day_without_changing_selections(monkeypatch,tmp_path):
 w=draft_workspace();w['requirements'].update(start_date='2026-10-09',days=2);w['selected_spots']=['a'];w['selected_return']['departure']='2026-10-10 12:00';w['selected_return']['arrival']='2026-10-10 16:00';calls=[]
 async def tool(name,args):
  if name=='retrieve_guides':return {'items':[]}
  return {'mode':args['mode'],'available':True,'minutes':60,'distance':20000}
 async def model(messages,**kw):
  if '独立审核' in messages[0]['content']:return {'content':json.dumps({'issues':[]})},{}
  calls.append(json.loads(messages[1]['content']))
  dt='2026-10-10' if len(calls)==1 else '2026-10-09'
  return {'content':json.dumps({'days':[{'date':dt,'items':[{'candidate_id':'a','duration':30}]}]})},{}
 monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 p=asyncio.run(planning.generate(w,lambda _:None))
 # 模型第一次把景点放在中午返程的当天，容量校验会给出可换日期并要求修订；
 # 无论这次是模型自己改对还是程序按容量确定性重排，结果都必须是：
 # 景点落在可用那天、用户选择与班次不变。
 assert len(calls)>=1
 assert p['days'][0]['date']=='2026-10-09' and any(e['candidate_id']=='a' for e in p['days'][0]['events'] if e['kind']=='spot')
 assert w['selected_spots']==['a'] and w['selected_return']['departure']=='2026-10-10 12:00'
 assert 'planning_feedback' not in w
