import asyncio,copy
import pytest
from app import agent,journey,foods,discovery

def trip():return {'requirements':{'city':'杭州','origin':'郑州','start_date':'2026-10-10','days':3,'adults':1},'catalog':{},'selected_spots':[],'messages':[],'tickets':{}}

def test_noon_train_controls_are_actual_query_conditions(monkeypatch):
 w=trip();seen=[]
 async def provider(s,t,args):seen.append(args);return {'data':{'data':[]},'source':{}}
 monkeypatch.setattr(agent,'tuniu',provider)
 async def weather(*args):pass
 monkeypatch.setattr(agent,'ensure_weather',weather)
 asyncio.run(agent.execute({'workspace':w,'text':'我打算中午走，你能查到相关的高铁票么','intent':{'action':'train','patch':{},'answer':'查询中午高铁'},'progress':lambda _:None}))
 assert seen[0]['departureTime']=='11:00-14:00'
 assert w['query_controls']['train_type']=='highspeed' and w['query_controls']['direction']=='outbound'

def test_date_range_and_local_origin_are_recorded():
 w=trip();w['requirements']={'city':'杭州'}
 intent=journey.refine_intent(w,'我从杭州出发，就在杭州玩，10号到12号',{'action':'chat','patch':{'city':'杭州'},'answer':''})
 agent.update_requirements(w,intent['patch'])
 assert w['requirements']['origin']=='杭州' and w['requirements']['days']==3 and w['requirements']['start_date']=='2026-10-10'
 assert journey.is_local(w['requirements'])

def test_long_trip_and_more_than_ten_spots_are_supported():
 w=trip();agent.update_requirements(w,{'days':21})
 w['catalog']={str(i):{'id':str(i),'kind':'spot','name':'景点'+str(i),'location':'120,30'} for i in range(12)}
 for i in w['catalog']:asyncio.run(agent.handle(w,'select',{'id':i},lambda _:None))
 assert len(w['selected_spots'])==12 and w['requirements']['days']==21

def test_meal_search_uses_current_day_or_explicit_anchor(monkeypatch):
 w=trip();w['catalog']={'a':{'id':'a','kind':'spot','name':'杜甫草堂','location':'104,30'},'b':{'id':'b','kind':'spot','name':'主要景点','location':'104.1,30.1'}};w['selected_spots']=['a','b']
 w['plan']={'days':[{'date':'2026-10-11','events':[{'kind':'spot','candidate_id':'b','start':'10:00','end':'12:00'}]}]};seen=[]
 async def tool(name,args):seen.append(args);return {'items':[]}
 monkeypatch.setattr(foods,'local_tool',tool)
 asyncio.run(foods.search(w,{'meal_date':'2026-10-11','meal_period':'lunch'},lambda _:None,None))
 assert seen[0]['location']=='104.1,30.1' and w['food_query']['anchor']=='主要景点'


def test_parent_branch_grouping_prefers_real_ids():
 w=trip();w['catalog']={'parent':{'id':'parent','kind':'spot','name':'龙门石窟'},'a':{'id':'a','kind':'spot','name':'礼佛台','parent_id':'parent'},'b':{'id':'b','kind':'spot','name':'万佛洞','parent_id':'parent'}};w['spot_search']={'ids':['a','b'],'page':1}
 g=discovery.groups(w);assert len(g)==1 and g[0]['parent_id']=='parent' and g[0]['basis']=='地图父子关系'
 assert set(discovery.page_info(w)['ids'])=={'parent','a','b'}
 w['catalog']['a'].pop('parent_id');w['catalog']['b'].pop('parent_id');w['catalog']['a']['name']='龙门石窟·礼佛台';w['catalog']['b']['name']='龙门石窟·万佛洞'
 assert '待核实' in discovery.groups(w)[0]['basis']


def test_same_city_does_not_query_intercity_provider(monkeypatch):
 w=trip();w['requirements']['origin']='杭州市'
 async def fail(*args):raise AssertionError('本地游不应调用城际票查询')
 monkeypatch.setattr(agent,'tuniu',fail)
 answer=asyncio.run(agent.handle(w,'train',{},lambda _:None))
 assert '同一区域' in answer


def test_long_plan_proposals_are_batched_and_keep_all_ids(tmp_path):
 import json
 from datetime import date,timedelta
 from app.proposals import create
 calls=[];spots=[{'id':str(i),'name':'地点'+str(i)} for i in range(35)];dates=[(date(2026,10,10)+timedelta(days=i)).isoformat() for i in range(21)]
 async def model(messages,**args):
  payload=json.loads(messages[1]['content']);calls.append(payload)
  grouped={d:[] for d in payload['tour_dates']}
  for n,p in enumerate(payload['spots']):grouped[payload['tour_dates'][n%len(payload['tour_dates'])]].append({'candidate_id':p['id'],'duration':60})
  return {'content':json.dumps({'title':'分阶段旅行','days':[{'date':d,'items':items} for d,items in grouped.items() if items]})},{}
 w=trip();w['requirements'].update(start_date=dates[0],days=len(dates))
 draft,groups,usage=asyncio.run(create(w,spots,{'dates':dates,'tour_dates':dates},'约束',lambda _:None,model,tmp_path))
 assert len(calls)==3 and max(len(p['spots']) for p in calls)<=16
 assert {i['candidate_id'] for d in groups for i in d['items']}=={p['id'] for p in spots}
 assert len({d['date'] for d in groups})==17


def test_excess_selection_and_distance_produce_soft_warnings():
 w=trip();w['requirements']['days']=2;w['catalog']={str(i):{'id':str(i),'kind':'spot','name':'地点'+str(i),'location':str(120+i*.1)+',30'} for i in range(10)};w['selected_spots']=list(w['catalog'])
 info=journey.selection_assessment(w)
 assert info['level']=='warning' and len(info['messages'])==2 and info['spread_km']>50
