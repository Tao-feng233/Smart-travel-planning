import asyncio,json
from app import journey,storage

def ready():
 return {'requirements':{'city':'杭州','origin':'郑州','start_date':'2026-10-10','days':3,'adults':1},'catalog':{},'selected_spots':['s'],'spots_confirmed':True,'stay_skipped':True,'selected_transport':{'selection_status':'confirmed'},'selected_return':{'selection_status':'confirmed'}}

def test_welcome_is_saved_message(monkeypatch):
 monkeypatch.setattr(storage,'save',lambda w:None)
 w=storage.new_workspace('test')
 assert w['messages'] and '您想去哪里' in w['messages'][0]['content']

def test_food_is_offered_before_plan():
 w=ready()
 assert journey.next_step(w)['view']=='food'
 w['dining_reviewed']=True
 assert journey.next_step(w)['action']=='plan'

def test_generated_plan_guidance_is_review():
 w=ready();w['plan']={'stale':False}
 step=journey.next_step(w)
 assert '查看' in step['message'] and '调整' in step['message'] and step.get('action')!='plan'

def test_stream_does_not_echo_acknowledgement_twice(monkeypatch):
 from app import replies
 w=ready();w['turn_action']='chat';w['last_action']='chat';w['ui']={};sink=[];prefix='好的，记录日期。\n已收集信息。\n\n';raw='好的，记录日期。\n\n已收集信息。\n\n请先完成当前选择。'
 async def model(messages,on_delta,**args):
  for char in raw:on_delta(char)
  return raw,{}
 monkeypatch.setattr(replies,'llm_stream',model);token=replies.PREFIX.set(prefix);other=replies.SINK.set(sink.append)
 try:
  result=asyncio.run(replies.compose(w,'完成'));assert result.count('好的，记录日期。')==1
  assert ''.join(sink).strip()=='请先完成当前选择。'
 finally:replies.PREFIX.reset(token);replies.SINK.reset(other)

def test_named_day_request_does_not_change_trip_dates():
 from app import agent,visits
 w=ready();w['catalog']={'s':{'id':'s','name':'西湖','kind':'spot','location':'120.14,30.25'}}
 i=journey.refine_intent(w,'第二天晚上去西湖',{'action':'chat','patch':{'start_date':'2026-10-11'},'answer':''})
 assert i['action']=='visit_schedule' and not i['patch']
 asyncio.run(agent.handle(w,i['action'],i,lambda _:None))
 assert w['visit_requests']['s']=={'date':'2026-10-11','period':'evening'}
 assert w['requirements']['start_date']=='2026-10-10'
 assert journey.refine_intent(w,'第二天晚上在西湖附近吃饭',{'action':'search_foods','patch':{},'answer':''})['action']=='search_foods'
 requests=[{'candidate_id':'s','date':'2026-10-10','period':'morning'},{'candidate_id':'b','date':'2026-10-11','period':'evening'}]
 i=journey.refine_intent(w,'第一天上午去西湖，第二天晚上去灵隐寺',{'action':'visit_schedule','patch':{'start_date':'2026-10-11'},'visit_requests':requests})
 assert i['visit_requests']==requests and not i['patch']

def test_dining_uses_dated_spot_and_hotel_for_evening():
 from app import foods
 w=ready();w['catalog']={'s':{'id':'s','name':'西湖','kind':'spot','location':'120.14,30.25'},'b':{'id':'b','name':'灵隐寺','kind':'spot','location':'120.10,30.23'}};w['selected_spots']=['s','b'];w['visit_requests']={'b':{'date':'2026-10-11','period':'afternoon'}}
 w['hotel']={'id':'h','name':'酒店','location':'120.15,30.26'}
 assert [p['id'] for p in foods.anchors(w,{'meal_date':'2026-10-11','meal_period':'dinner'})]==['b','h']

def test_proposal_repairs_wrong_requested_day(tmp_path):
 from app.proposals import create
 w=ready();w['visit_requests']={'s':{'date':'2026-10-11','period':'evening'}};seen=[]
 async def model(messages,**kwargs):
  seen.append(messages)
  return {'content':json.dumps({'days':[{'date':'2026-10-10' if len(seen)==1 else '2026-10-11','items':[{'candidate_id':'s','duration':60}]}]})},{}
 dates=['2026-10-10','2026-10-11','2026-10-12']
 _,groups,_=asyncio.run(create(w,[{'id':'s'}],{'dates':dates,'tour_dates':dates},'test',lambda _:None,model,tmp_path))
 assert len(seen)==2 and groups[0]['date']=='2026-10-11' and groups[0]['items'][0]['period']=='evening'

def test_map_uses_saved_coordinates_and_never_exposes_key():
 from app import maps
 w=ready();w['catalog']={'s':{'id':'s','name':'西湖','location':'120.14,30.25'},'bad':{'id':'bad','location':'nan,30'}}
 assert not maps.coordinate(w['catalog']['bad'])
 p=maps.params(maps.points(w),True)
 assert 'key' not in p and '120.14,30.25' in p['markers']

def test_evening_visit_keeps_lunch_and_correct_time(monkeypatch,tmp_path):
 from app import planning
 w=ready();w['requirements']['days']=1;w['catalog']={'s':{'id':'s','kind':'spot','name':'西湖','location':'120.14,30.25'}};w['visit_requests']={'s':{'date':'2026-10-10','period':'evening'}};w.pop('selected_transport');w.pop('selected_return')
 async def tool(*args):return {'items':[]}
 async def model(messages,**args):
  if '独立审核' in messages[0]['content']:return {'content':json.dumps({'issues':[]})},{}
  return {'content':json.dumps({'days':[{'date':'2026-10-10','items':[{'candidate_id':'s','duration':60}]}]})},{}
 monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
 plan=asyncio.run(planning.generate(w,lambda _:None));events=plan['days'][0]['events']
 assert next(e for e in events if e['kind']=='spot')['start']=='18:00'
 assert any(e['kind']=='meal' and e['name'].startswith('午餐') for e in events)
