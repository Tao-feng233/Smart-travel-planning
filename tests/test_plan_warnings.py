import asyncio
import copy
import json
import pytest

from app.proposals import create
from app import plan_warnings, planning
from app.providers import DataError


def trip():
    return {'id':'warning-trip','requirements':{'city':'青岛','start_date':'2026-10-12','days':3},
        'catalog':{i:{'id':i,'kind':'spot','name':n,'location':'120.3,36.0'} for i,n in
                   [('a','海滨风景区'),('b','金沙滩'),('c','信号山公园'),('d','崂山风景区')]},
        'selected_spots':['a','b','c','d'],'selected_transport':{'id':'t','name':'G测试','arrival':'2026-10-11 11:00','departure':'2026-10-11 08:00','selection_status':'confirmed'}}


def test_three_occupied_tour_days_with_early_arrival_are_advisory_not_generation_failure(tmp_path):
    w=trip();calls=[]
    days=[{'date':'2026-10-12','items':[{'candidate_id':'a','duration':60}]},
          {'date':'2026-10-13','items':[{'candidate_id':'b','duration':120},{'candidate_id':'c','duration':120}]},
          {'date':'2026-10-14','items':[{'candidate_id':'d','duration':150}]}]
    async def model(messages,**kwargs):calls.append(messages);return {'content':json.dumps({'days':days})},{}
    ds=['2026-10-12','2026-10-13','2026-10-14'];before=copy.deepcopy(w)
    draft,groups,_=asyncio.run(create(w,list(w['catalog'].values()),{'dates':['2026-10-11']+ds,'tour_dates':ds},'规划',lambda _:None,model,tmp_path))
    assert w==before and {g['date'] for g in groups}==set(ds)
    assert draft['planning_issues'][0]['level']=='warning'
    assert draft['planning_issues'][0]['code']=='unbalanced_estimate'
    assert '2026-10-11' not in draft['planning_issues'][0]['message']
    assert '2026-10-13' in draft['planning_issues'][0]['message'] and '2026-10-12' in draft['planning_issues'][0]['message']


def test_estimated_capacity_shortfall_keeps_valid_draft_for_user_confirmation(tmp_path):
    w=trip();w['requirements']['days']=1;w['selected_spots']=['d']
    async def model(*args,**kwargs):return {'content':json.dumps({'days':[{'date':'2026-10-12','items':[{'candidate_id':'d','duration':420}]}]})},{}
    draft,groups,_=asyncio.run(create(w,[w['catalog']['d']],{'dates':['2026-10-12'],'tour_dates':['2026-10-12']},'规划',lambda _:None,model,tmp_path))
    assert groups[0]['items'][0]['duration']==420
    assert draft['planning_issues'][0]['code']=='estimated_capacity'


def cached_plan():
    return {'title':'带提醒的草稿','days':[],'warnings':[],
            'planning_issues':[{'code':'estimated_capacity','level':'warning','message':'估算偏紧','candidate_ids':['d'],'view':'spot','date':'2026-10-12'}]}


def test_warning_draft_is_not_published_until_explicit_confirmation():
    w=trip();w['plan']={'title':'原计划'};before=copy.deepcopy(w['plan'])
    assert plan_warnings.request(w,cached_plan())
    assert w['plan']==before
    nonce=w['pending_plan_warning']['id']
    with pytest.raises(DataError):plan_warnings.approve(w,{'approval_id':nonce})
    with pytest.raises(DataError):plan_warnings.approve(w,{'approval_id':'forged','confirmed':True})
    plan_warnings.approve(w,{'approval_id':nonce,'confirmed':True})
    assert w['plan']['title']=='带提醒的草稿' and w['plan']['warning_acceptance']['confirmed']
    assert any('估算偏紧' in s for s in w['plan']['warnings'])
    assert 'pending_plan_warning' not in w
    with pytest.raises(DataError):plan_warnings.approve(w,{'approval_id':nonce,'confirmed':True})


def test_cancel_or_changed_inputs_keeps_old_plan_and_selections():
    w=trip();w['plan']={'title':'原计划'};choices=copy.deepcopy(w['selected_spots'])
    plan_warnings.request(w,cached_plan());plan_warnings.cancel(w)
    assert w['plan']['title']=='原计划' and w['selected_spots']==choices
    plan_warnings.request(w,cached_plan());nonce=w['pending_plan_warning']['id'];w['requirements']['days']=4
    with pytest.raises(DataError,match='已变化'):plan_warnings.approve(w,{'approval_id':nonce,'confirmed':True})
    assert w['plan']['title']=='原计划' and w['selected_spots']==choices


def test_invalid_model_identity_is_not_downgraded_to_a_warning(tmp_path):
    w=trip()
    async def model(*args,**kwargs):return {'content':json.dumps({'days':[{'date':'2026-10-12','items':[{'candidate_id':'foreign','duration':90}]}]})},{}
    with pytest.raises(DataError) as failure:
        asyncio.run(create(w,list(w['catalog'].values()),{'dates':['2026-10-12'],'tour_dates':['2026-10-12']},'规划',lambda _:None,model,tmp_path))
    assert failure.value.context['model_output_error']
    assert 'pending_plan_warning' not in w


def test_early_arrival_day_is_in_book_but_not_workload_balancing(monkeypatch,tmp_path):
    w=trip();w['selected_spots']=['a','b','c']
    async def model(*args,**kwargs):
        value={'issues':[],'summary':'待核实'} if kwargs.get('label')=='review' else {
            'days':[{'date':'2026-10-'+str(n),'items':[{'candidate_id':cid,'duration':90}]} for n,cid in zip([12,13,14],w['selected_spots'])]}
        return {'content':json.dumps(value)},{}
    async def tool(*args,**kwargs):return {'items':[]}
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    result=asyncio.run(planning.generate(w,lambda _:None))
    assert [d['date'] for d in result['days']]==['2026-10-11','2026-10-12','2026-10-13','2026-10-14']
    assert not any(e['kind']=='spot' for e in result['days'][0]['events'])
    assert result['planning_issues']==[]
