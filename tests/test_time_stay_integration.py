import asyncio
import copy
import json
import time
import pytest
from app import agent,foods,planning,schedule,stay_plan,travel_preview,transport_links,visit_analysis,timeline_review,plan_warnings

D1,D2='2026-10-12','2026-10-13'


def trip():
    cat={cid:{'id':cid,'kind':'hotel' if cid.startswith('h') else 'food' if cid=='f' else 'spot','name':cid,'location':f'120.{300+i},36.05'} for i,cid in enumerate(['h1','h2','a','b','f'])}
    for cid in ('h1','h2'):cat[cid].update(provider_id=cid,price=100 if cid=='h1' else 300,query_conditions={'checkIn':D1,'checkOut':'2026-10-14'})
    return {'id':'synthetic','revision':1,'requirements':{'city':'青岛','start_date':D1,'days':2,'adults':2,'day_end':'18:30'},
        'catalog':cat,'hotel':cat['h2'],'selected_spots':['a','b'],'stay_hotels':{D1:'h1',D2:'h2'},
        'visit_requests':{'a':{'date':D1},'b':{'date':D2}},'meal_choices':{},'messages':[]}


async def road(a,b):return [{'mode':'driving','minutes':20,'available':True,'status':'available','source':{'queried_at':'synthetic'}}]


def test_authoritative_assignments_replace_cached_rows_without_fabricating_unassigned_facts():
    w=trip();w['stay_plan']=stay_plan.plan(w)
    stay_plan.assign(w,'h2',[D1]);assert stay_plan.assignment_map(w)[D1]=='h2'
    w['stay_hotels'].pop(D2);assert stay_plan.facts(w)[D2]['hotel']['id'] is None
    assert stay_plan.hotel_for(w,D2) is None
    assert stay_plan.hotel_for(w,D2,morning=True)['id']=='h2'


def test_nightly_routes_budget_and_checkout_are_consistent(monkeypatch):
    w=trip();seen=[]
    async def route(a,b):seen.append((a['id'],b['id']));return await road(a,b)
    monkeypatch.setattr(planning,'route_options',route)
    plan=asyncio.run(planning._generate(w,lambda _:None,preview=True))
    assert ('a','h1') in seen and ('h1','b') in seen and ('b','h2') in seen
    assert plan['budget']['hotel_reference']==400
    assert plan['nightly_stays']=={D1:'h1',D2:'h2'}
    day=next(d for d in plan['days'] if d['date']==D2)
    assert not any('重叠' in x for x in planning.validate_plan(plan,w['requirements']))
    starts=[planning.minute(e['start']) for e in day['events']]
    assert starts==sorted(starts)
    w['catalog']['h2']['provider_id']='h1'
    plan=asyncio.run(planning._generate(w,lambda _:None,preview=True))
    assert not any('换酒店前' in e['name'] for d in plan['days'] for e in d['events'])


def test_breakfast_requires_previous_night_hotel_dates_and_explicit_entitlement():
    w=trip();room={'hotel_id':'h1','meal':'含双早','quantity':1,'query_conditions':{'checkIn':D1,'checkOut':D2}}
    w['selected_rooms']={'h1':room}
    assert not foods.included_meal(w,D1)['included']
    assert foods.included_meal(w,D2)['included']
    w['meal_choices'][D2+'|breakfast']={'mode':'chosen','food_id':'f'}
    assert not foods.included_meal(w,D2)['included']
    w['meal_choices']={};room['meal']='含餐：晚餐';assert not foods.included_meal(w,D2)['included']
    room['meal']='含双早';room['query_conditions']={};assert not foods.included_meal(w,D2)['included']
    room['query_conditions']={'checkIn':D1,'checkOut':D2};w['stay_hotels'][D1]='h2'
    assert not foods.included_meal(w,D2)['included']


def test_lodging_skip_city_reset_and_invalid_explicit_night_preserve_intent():
    w=trip();before=copy.deepcopy(w['stay_hotels'])
    with pytest.raises(agent.DataError):asyncio.run(agent.handle(w,'select',{'id':'h1','stay_date':'2026-10-20'},lambda _:None))
    assert w['stay_hotels']==before
    w['requirements']['local_trip']=True
    asyncio.run(agent.handle(w,'skip_hotel',{},lambda _:None));assert not w.get('stay_hotels') and not w.get('hotel')
    w=trip();agent.update_requirements(w,{'city':'杭州'})
    assert not w.get('stay_hotels') and not w.get('selected_rooms') and not w.get('stay_plan')


def test_nightly_change_invalidates_route_analysis_and_warning_confirmation():
    w=trip();a=visit_analysis.signature(w);b=travel_preview.signature(w);c=transport_links.signature(w)
    plan={'days':[],'planning_issues':[{'code':'estimated_capacity','message':'偏紧'}]}
    assert plan_warnings.request(w,plan)
    pending=w['pending_plan_warning']['id'];w['stay_hotels'][D1]='h2'
    assert a!=visit_analysis.signature(w) and b!=travel_preview.signature(w) and c!=transport_links.signature(w)
    with pytest.raises(agent.DataError):plan_warnings.approve(w,{'approval_id':pending,'confirmed':True})


def test_suggested_day_end_is_warning_but_return_deadline_is_real_conflict(monkeypatch):
    w=trip();w['requirements']['days']=1;w['selected_spots']=['a'];w['visit_requests']={'a':{'date':D1}}
    w['meal_choices']={D1+'|dinner':{'mode':'chosen','food_id':'f'}}
    monkeypatch.setattr(planning,'route_options',road)
    plan=asyncio.run(planning._generate(w,lambda _:None,preview=True))
    assert any(x['code']=='revision_day_end' for x in plan['planning_issues'])
    assert any(e.get('food',{}).get('id')=='f' for e in plan['days'][0]['events'])
    w['selected_return']={'id':'back','kind':'train','departure':D1+' 18:30','arrival':D1+' 21:00','selection_status':'confirmed'}
    with pytest.raises(agent.DataError):asyncio.run(planning._generate(w,lambda _:None,preview=True))


def test_afternoon_arrival_audit_is_read_only_bounded_and_deduplicates_warnings():
    w=trip();w['selected_transport']={'id':'out','kind':'train','name':'G1','arrival':D1+' 14:20','departure':D1+' 10:00','selection_status':'confirmed'}
    w['visit_requests']['a']['period']='morning'
    before=copy.deepcopy(w)
    async def model(*a,**k):return {'content':json.dumps({'summary':'首日宜轻松','issues':[{'date':D1,'candidate_ids':['a'],'view':'spot','impact':'major','message':'建议把较长游览移到第二天，固定日期需用户确认。'}]},ensure_ascii=False)},{}
    result=asyncio.run(timeline_review.refresh(w,model,lambda _:None))
    assert result['status']=='completed' and any(x['code']=='late_arrival' for x in result['issues'])
    assert all(w.get(k)==before.get(k) for k in ['requirements','selected_spots','stay_hotels','selected_transport','visit_requests','plan'])
    assert timeline_review.fresh_issues(w,result)
    assert timeline_review.fresh_issues(w,result)==[]
    w['catalog']['b']['location']='120.6,36.07';assert timeline_review.current(w) is None


@pytest.mark.parametrize('raw',['[]','null','"text"','{"issues":[{"candidate_ids":["missing"],"message":"bad"}]}'])
def test_bad_audit_response_falls_back_without_failing_selection(raw):
    w=trip();before=copy.deepcopy(w['stay_hotels'])
    async def model(*a,**k):return {'content':raw},{}
    result=asyncio.run(timeline_review.refresh(w,model,lambda _:None))
    assert result['status']=='model_unavailable' and w['stay_hotels']==before
