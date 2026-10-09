import asyncio
import copy
import json
import pytest
from app import planning,schedule,visit_analysis,travel_preview,timeline_tools,timeline_review,plan_warnings

DT='2026-10-14'

def trip():
 cat={'h':{'id':'h','name':'酒店','kind':'hotel','location':'120.30,36.05'},
      'a':{'id':'a','name':'五四广场','kind':'spot','location':'120.35,36.06'},
      'b':{'id':'b','name':'电视塔','kind':'spot','location':'120.36,36.07'}}
 w={'requirements':{'city':'青岛','start_date':DT,'days':1,'adults':2},'catalog':cat,'selected_spots':['a','b'],'hotel':cat['h'],
    'visit_requests':{'a':{'date':DT,'period':'morning'},'b':{'date':DT,'period':'afternoon'}},'meal_choices':{},'messages':[]}
 w['visit_analysis']={'signature':visit_analysis.signature(w),'status':'model','day_pacing':[],'notices':[],'items':[
    {'candidate_id':cid,'date':DT,'period':period,'duration':duration,'basis':'model_estimate','reason':'原建议'} for cid,period,duration in [('a','morning',150),('b','afternoon',120)]]}
 return w


def changes():return {'items':[{'candidate_id':'a','date':DT,'period':'morning','duration':60,'not_before':'10:15','sequence':1,'reason':'重点观景拍照，不包含其他区域游览'},
 {'candidate_id':'b','date':DT,'period':'afternoon','duration':120,'sequence':2,'reason':'保留完整参观体验'}],
 'day_pacing':[{'date':DT,'lunch_time':'12:15','lunch_minutes':60,'rest_minutes':45,'break_minutes':15,'reason':'错开游览与用餐，保留休息'}],'reason':'根据已查路程，调整广场体验范围与午餐时间。'}


async def road(a,b):return [{'mode':'driving','minutes':40,'status':'available','available':True,'source':{'queried_at':'synthetic'}}]


def test_model_calls_timeline_tool_and_rechecks_actual_roads_before_applying(monkeypatch):
 w=trip();before=copy.deepcopy({k:w.get(k) for k in timeline_tools.PROTECTED});calls=[]
 monkeypatch.setattr(planning,'route_options',road)
 async def model(messages,**kwargs):
  calls.append((messages,kwargs));return {'tool_calls':[{'id':'edit','function':{'name':'adjust_timeline','arguments':json.dumps(changes(),ensure_ascii=False)}}]},{}
 asyncio.run(travel_preview.refresh(w,lambda _:None,model=model,optimize=True))
 assert w['timeline_adjustment']['status']=='applied' and w['travel_preview']['status']=='ready'
 assert calls[0][1]['tools'][0]['function']['name']=='adjust_timeline'
 context=json.loads(calls[0][0][1]['content']);assert context['conflict']['context']['available_minutes']<150
 assert any(e['route']['minutes']==40 for e in context['conflict']['context']['events'] if e['kind']=='route')
 timeline=schedule.build(w);spots={x['candidate_id']:x for x in timeline['entries'] if x['kind']=='spot'}
 assert spots['a']['time']=='10:15' and spots['a']['end']=='11:15' and spots['b']['end']<='18:00'
 assert any(x['kind']=='route' and x['mode']=='driving' and x['route_minutes']==40 for x in timeline['entries'])
 assert next(x for x in timeline['meal_slots'] if x['period']=='lunch')['time']=='12:15'
 assert all(w.get(k)==v for k,v in before.items())


def test_invalid_edit_has_no_partial_mutation_and_one_tool_feedback_retry(monkeypatch):
 w=trip();before=copy.deepcopy(w);bad=changes();bad['items'][0]['period']='afternoon'
 with pytest.raises(planning.DataError):asyncio.run(timeline_tools.apply(w,bad,lambda _:None))
 assert w==before
 monkeypatch.setattr(planning,'route_options',road);calls=[]
 async def model(messages,**kwargs):
  calls.append(copy.deepcopy(messages));data=bad if len(calls)==1 else changes()
  return {'tool_calls':[{'id':str(len(calls)),'function':{'name':'adjust_timeline','arguments':json.dumps(data)}}]},{}
 result=asyncio.run(timeline_tools.optimize(w,model,lambda _:None,force=True))
 assert result['status']=='applied' and len(calls)==2 and 'tool_validation_feedback' in calls[1][-1]['content']
 assert any(m['role']=='tool' and json.loads(m['content'])['applied'] is False for m in calls[1])


def test_unqueried_travel_is_visible_without_fabricating_a_clock_or_mode():
 w=trip();rows=schedule.build(w)['entries'];roads=[x for x in rows if x['kind']=='unknown_route']
 assert roads and all(x['time']=='' and x['end'] is None and x['mode'] is None and x['route_minutes'] is None for x in roads)
 assert roads[0]['name']=='酒店 → 五四广场'


def test_minor_overload_and_uneven_distribution_do_not_require_warning_approval():
 w=trip();plan={'days':[],'planning_issues':[{'code':'estimated_capacity','level':'warning','overrun_minutes':15,'available_minutes':400},
       {'code':'unbalanced_estimate','level':'warning'}]}
 assert not plan_warnings.request(w,plan)
 plan['planning_issues'][0]['overrun_minutes']=120
 assert plan_warnings.request(w,plan)


def test_afternoon_arrival_without_material_conflict_does_not_raise_a_warning():
 w=trip();w['selected_transport']={'id':'out','kind':'train','arrival':DT+' 14:20','selection_status':'confirmed'}
 timeline={'entries':[{'date':DT,'kind':'spot','candidate_id':'b','time':'15:50','end':'16:20','duration':30}], 'conflicts':[]}
 assert timeline_review.checks(w,timeline)==[]


def test_route_and_arrival_keys_are_unique_and_sightseeing_duration_stays_separate():
 w=trip();plan={'days':[{'date':DT,'events':[{'kind':'arrival','candidate_id':'h','start':'08:00','end':'08:30'},
   {'kind':'route','candidate_id':'h','name':'车站 → 酒店','start':'08:30','end':'09:00','route':{'mode':'driving','minutes':20},'buffer':10},
   {'kind':'spot','candidate_id':'a','start':'09:00','end':'10:00','duration':60}]}]}
 rows=schedule.plan_rows(w,plan,True);assert len({x['key'] for x in rows})==len(rows)
 assert next(x for x in rows if x['kind']=='spot')['duration']==60
 assert next(x for x in rows if x['kind']=='route')['route_minutes']==20


def test_semantic_edit_plan_mode_keeps_explicit_timeline_tool_action():
 from app import goal_agent
 w=trip();intent={'action':'adjust_timeline','patch':{},'mission':{'mode':'edit_plan','objective':'调整时间轴'}}
 assert goal_agent.normalize(w,'调整时间轴',intent)['action']=='adjust_timeline'


def test_explicit_timeline_edit_invalidates_prepared_warning_book(monkeypatch):
 w=trip();draft={'days':[],'planning_issues':[{'code':'estimated_capacity','level':'warning','message':'严重不足'}]}
 assert plan_warnings.request(w,draft)
 nonce=w['pending_plan_warning']['id'];monkeypatch.setattr(planning,'route_options',road)
 asyncio.run(timeline_tools.apply(w,changes(),lambda _:None))
 with pytest.raises(planning.DataError):plan_warnings.approve(w,{'approval_id':nonce,'confirmed':True})


def test_model_evening_suggestion_uses_consistent_window_and_keeps_train_deadline():
 w=trip();w['visit_requests']={}
 proposal={'items':[{'candidate_id':'a','date':DT,'period':'evening','duration':60,'not_before':'19:00','reason':'广场晚间观景建议，现场条件待核实'}],'reason':'晚间体验'}
 working=timeline_tools.prepare(w,proposal)
 assert schedule.day_end(working,DT)==22*60
 working['selected_return']={'id':'back','kind':'train','departure':DT+' 20:00','selection_status':'confirmed'}
 assert schedule.windows(working,DT)[1]==18*60
