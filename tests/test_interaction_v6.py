import asyncio,copy
import pytest
from app import agent,discovery,choices

def work():
 return {'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':3,'adults':1,'preferences':['海边','海鲜']},'catalog':{},'selected_spots':[],'messages':[],'tickets':{},'hotel':{'id':'h1','kind':'hotel','name':'酒店'},'selected_room':{'id':'r1','quantity':1},'selected_transport':{'id':'go','kind':'train','direction':'outbound','arrival':'2026-10-12 10:00','selection_status':'confirmed'},'selected_return':{'id':'back','kind':'train','direction':'return','departure':'2026-10-14 12:00','selection_status':'confirmed'}}

def test_return_date_shift_never_changes_trip_start_or_lodging(monkeypatch):
 w=work();before=copy.deepcopy(w)
 async def handle(w,a,args,p):return ''
 async def weather(*args):pass
 monkeypatch.setattr(agent,'handle',handle);monkeypatch.setattr(agent,'ensure_weather',weather)
 asyncio.run(agent.execute({'workspace':w,'text':'返程给我往后一天随便选一个吧','intent':{'action':'search_spots','patch':{'start_date':'2026-10-15'},'answer':'已记录'},'progress':lambda _:None}))
 assert w['requirements']['start_date']==before['requirements']['start_date']
 assert w['requirements']['return_date']=='2026-10-15'
 assert w['hotel']==before['hotel'] and w['selected_room']==before['selected_room'] and w['selected_transport']==before['selected_transport']

def test_preferences_are_accumulated_across_refinements():
 w=work();agent.update_requirements(w,{'preferences':['知名度较高']})
 assert '海鲜' in w['requirements']['preferences'] and '海边' in w['requirements']['preferences']

def test_default_return_is_day_after_play_days(monkeypatch):
 seen=[]
 async def tuniu(s,t,p):seen.append(p);return {'data':{'data':[]},'source':{}}
 monkeypatch.setattr(agent,'tuniu',tuniu)
 asyncio.run(agent.handle(work(),'train',{'direction':'return'},lambda _:None))
 assert seen[0]['departureDate']=='2026-10-15'

def test_return_date_change_invalidates_only_return():
 w=work();before=copy.deepcopy(w);agent.update_requirements(w,{'return_date':'2026-10-15'})
 assert w['requirements']['return_date']=='2026-10-15' and w['selected_return'] is None
 assert w['selected_transport']==before['selected_transport'] and w['selected_room']==before['selected_room']

def test_paging_does_not_fetch_unrecommended_candidates(monkeypatch):
 w=work();w['catalog']={str(i):{'id':str(i),'kind':'spot','name':'景点'+str(i)} for i in range(4)}
 w['spot_search']={'ids':list(w['catalog']),'page':1,'exhausted':False,'keywords':['海边'],'provider_page':1}
 async def tool(*args):raise AssertionError('翻页不应查询新数据')
 monkeypatch.setattr(discovery,'local_tool',tool)
 with pytest.raises(agent.DataError,match='推荐|更多'):
  asyncio.run(discovery.turn_page(w,{'page':2},lambda _:None,None))


def test_food_preferences_survive_known_scenic_refinement_and_types_stay_separate(monkeypatch):
 from app import foods,providers
 w=work();w['catalog']['s1']={'id':'s1','kind':'spot','name':'栈桥','location':'120,36'};w['selected_spots']=['s1'];calls=[]
 async def tool(name,args):
  calls.append(args)
  if args['category']=='market':return {'items':[]}
  return {'items':[{'id':'f'+str(i),'kind':'food','name':'餐厅'+str(i),'location':'120,36'} for i in range(6)]}
 async def rank(w,items,*args):
  for i,p in enumerate(items):p['recommendation_rank']=i
 monkeypatch.setattr(foods,'local_tool',tool)
 asyncio.run(foods.search(w,{'keywords':['海鲜']},lambda _:None,rank))
 assert len(w['food_query']['ids'])==5 and calls[0]['location']=='120,36' and calls[0]['category']=='food'
 assert 'f0' not in w['selected_spots']
 from app.journey import refine_intent
 i=refine_intent(w,'感觉这几个地方好像不太出名啊，都没太听过',{'action':'spots_page','patch':{'preferences':['知名度高']}})
 agent.update_requirements(w,i['patch'])
 assert i['action']=='search_spots' and i['prefer_known'] and '海鲜' in w['requirements']['preferences']


def test_meals_are_optional_replaceable_and_can_be_cleared():
 from app import foods
 w=work();w['catalog'].update(f1={'id':'f1','kind':'food','name':'第一餐厅'},f2={'id':'f2','kind':'food','name':'第二餐厅'})
 for cid in ('f1','f2'):foods.select_meal(w,{'meal_date':'2026-10-13','meal_period':'lunch','food_id':cid})
 assert len(w['meal_choices'])==1 and w['meal_choices']['2026-10-13|lunch']['food_id']=='f2'
 foods.select_meal(w,{'meal_mode':'self'})
 assert w['meal_choices']=={} and foods.choice(w,'2026-10-13','lunch') is None


def test_natural_language_select_saves_hotel_and_confirms_transport(monkeypatch):
 w=work();w['hotel']=None;w['selected_room']=None;w['selected_transport']=None;w['selected_return']=None
 w['catalog']={'h1':{'id':'h1','kind':'hotel','name':'汉庭青岛酒店'},'t1':{'id':'t1','kind':'train','direction':'outbound','name':'G1852','departure':'2026-10-12 07:00','arrival':'2026-10-12 12:00'}};w['hotel_query']={'ids':['h1']};w['transport']={'items':[w['catalog']['t1']]}
 async def weather(*args):pass
 monkeypatch.setattr(agent,'ensure_weather',weather)
 for text,cid in [('帮我选择汉庭青岛酒店','h1'),('帮我选择G1852','t1')]:
  asyncio.run(agent.execute({'workspace':w,'text':text,'intent':{'action':'chat','patch':{},'answer':'知道了'},'progress':lambda _:None}))
 assert w['hotel']['id']=='h1' and w['selected_transport']['id']=='t1' and w['selected_transport']['selection_status']=='confirmed'


def test_next_step_requires_real_choice_and_does_not_repeat_weather():
 from app.journey import next_step,refine_intent
 w=work();w['catalog']['s']={'id':'s','name':'栈桥','kind':'spot'};w['selected_spots']=['s'];w['spots_confirmed']=True
 assert next_step(w)['view']=='food'
 w['dining_reviewed']=True
 assert next_step(w)['action']=='plan'
 i=refine_intent(w,'下一步该干什么',{'action':'search_spots','patch':{},'keywords':['海边']})
 assert i['action']=='chat' and i['view']=='plan'


def test_food_search_uses_verified_category_and_rejects_restaurants_as_spots(monkeypatch):
 from app import providers
 calls=[]
 async def amap(path,args):calls.append((path,args));return {'data':{'pois':[{'id':'x','name':'海鲜餐厅','typecode':'050100','type':'餐饮服务;中餐厅'}]},'source':{}}
 monkeypatch.setattr(providers,'amap',amap)
 rows=asyncio.run(providers.search_poi('青岛','海鲜','food',location='120,36'))
 assert rows[0]['kind']=='food' and calls[0][0]=='/v5/place/around' and calls[0][1]['types']=='050000'
 assert not asyncio.run(providers.search_poi('青岛','海边','spot'))


def test_plan_includes_selected_lunch_and_optional_meals_with_real_routes(monkeypatch,tmp_path):
 import json
 from app import planning,foods
 monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 async def model(messages,**kwargs):
  if '审核助手' in messages[0]['content']:return {'content':'{"issues":[],"summary":"请核对"}'},{}
  return {'content':json.dumps({'days':[{'date':'2026-10-12','items':[]},{'date':'2026-10-13','items':[{'candidate_id':'s','duration':90,'note':'建议沿海岸游览'}]},{'date':'2026-10-14','items':[]}],'packing':[],'todos':[]})},{}
 async def tool(*args):return {'items':[]}
 pairs=[]
 async def routes(a,b):
  pairs.append((a['id'],b['id']))
  return [{'available':True,'mode':'driving','minutes':13,'distance':4800,'source':{}}]
 monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'route_options',routes)
 w=work();w['catalog']={'s':{'id':'s','name':'栈桥','kind':'spot','location':'120,36'},'f':{'id':'f','name':'海鲜餐厅','kind':'food','location':'120.1,36.1','source':{}}};w['selected_spots']=['s'];w['hotel']={'id':'h','name':'酒店','location':'120.2,36.2','query_conditions':{'checkOut':'2026-10-14'}};w['selected_room']=None
 w['selected_transport']={'id':'go','name':'G1','departure':'2026-10-12 18:40','arrival':'2026-10-12 22:26'};w['selected_return']={'id':'back','name':'G2','departure':'2026-10-15 11:22','arrival':'2026-10-15 15:09'}
 foods.select_meal(w,{'meal_date':'2026-10-13','meal_period':'lunch','food_id':'f'})
 p=asyncio.run(planning.generate(w,lambda _:None));events=p['days'][1]['events']
 assert any(e['kind']=='meal' and e.get('food',{}).get('id')=='f' for e in events)
 assert ('h','f') in pairs and ('f','h') in pairs
 assert any('早餐' in e['name'] and '自行安排' in e['name'] for e in events)
 assert p['days'][-1]['date']=='2026-10-15' and any('延住' in x for x in p['warnings'])
 assert not any('重叠' in x for x in p['warnings'])
 foods.select_meal(w,{'meal_mode':'self'});again=asyncio.run(planning.generate(w,lambda _:None))
 assert not any(e.get('food') for d in again['days'] for e in d['events'])


def test_requery_same_effective_date_preserves_manual_confirmation(monkeypatch):
 w=work();w['selected_transport'].update(name='G1',departure='2026-10-12 07:00');w['selected_return'].update(name='G2',departure='2026-10-15 12:00')
 before=copy.deepcopy(w)
 async def provider(*args):return {'data':{'data':[]},'source':{}}
 monkeypatch.setattr(agent,'tuniu',provider)
 for direction,day in [('outbound','2026-10-12'),('return','2026-10-15')]:
  asyncio.run(agent.handle(w,'train',{'direction':direction,'departure_date':day},lambda _:None))
 assert w['selected_transport']==before['selected_transport'] and w['selected_return']==before['selected_return']
 assert w['selected_transport']['selection_status']=='confirmed' and w['selected_return']['selection_status']=='confirmed'


def test_natural_meal_choice_executes_once_and_preserves_room(monkeypatch):
 w=work();w['catalog']['f1']={'id':'f1','kind':'food','name':'栈桥海鲜餐厅'};w['food_query']={'ids':['f1']}
 async def weather(*args):pass
 monkeypatch.setattr(agent,'ensure_weather',weather)
 asyncio.run(agent.execute({'workspace':w,'text':'帮我选择栈桥海鲜餐厅作为10月13日午餐','intent':{'action':'meal_choice','patch':{},'meal_date':'2026-10-13','meal_period':'lunch','select_ids':['f1']},'progress':lambda _:None}))
 assert w['meal_choices']['2026-10-13|lunch']['food_id']=='f1' and w['selected_room']['id']=='r1'
