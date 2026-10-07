import copy
from datetime import date,timedelta
import pytest
from app.agent import update_requirements,unwrap
from app.planning import validate_plan,choose_route
from app.rag import retrieve
from app.providers import ALLOW
from app.report import markdown

def workspace():
    return {'requirements':{'city':'青岛','start_date':(date.today()+timedelta(days=2)).isoformat(),'days':2},
            'catalog':{'hotel:1':{'id':'hotel:1','kind':'hotel','name':'已选酒店'},'spot:1':{'id':'spot:1','kind':'spot','name':'景点','source':{'name':'测试来源','queried_at':'2026-10-05'}}},
            'hotel':{'id':'hotel:1','name':'已选酒店'},'selected_spots':['spot:1'],'plan':{'stale':False},'tickets':{},'transport':{},'selected_transport':{}}

def test_date_change_keeps_choices_but_invalidates_quote_and_plan():
    w=workspace();update_requirements(w,{'start_date':(date.today()+timedelta(days=3)).isoformat()})
    assert w['selected_spots']==['spot:1']
    assert w['hotel']['id']=='hotel:1' and w['hotel']['stale']
    assert w['catalog']['hotel:1']['stale'] and w['plan']['stale']
    assert w['selected_transport'] is None

def test_city_change_does_not_reuse_other_city_candidates():
    w=workspace();update_requirements(w,{'city':'杭州'})
    assert not w['catalog'] and not w['selected_spots'] and w['hotel'] is None
    assert w['plan']['stale']

def test_zero_budget_rejected_instead_of_silent_default():
    with pytest.raises(Exception,match='预算'):update_requirements(workspace(),{'budget':0})

def test_past_date_rejected():
    with pytest.raises(Exception,match='日期'):update_requirements(workspace(),{'start_date':'2020-01-01'})

def test_no_claim_of_exact_inventory_from_transport_wrapper():
    d=unwrap({'result':'{"data":[{"seatAvailable":{"edzNum":99}}]}'})
    assert d['data'][0]['seatAvailable']['edzNum']==99

def test_detect_overlap_and_day_overrun():
    p={'days':[{'date':'2026-10-08','events':[{'name':'活动一','start':'09:00','end':'10:00'},
                                            {'name':'活动二','start':'09:50','end':'19:00'}]}]}
    issues=validate_plan(p,{'day_end':'18:00'})
    assert any('重叠' in x for x in issues) and any('结束时间' in x for x in issues)

def test_relaxed_preference_limits_default_walking():
    options=[{'available':True,'mode':'walking','minutes':35},{'available':True,'mode':'transit','minutes':25},{'available':True,'mode':'driving','minutes':18}]
    assert choose_route(options,{'pace':'relaxed'})['mode']=='driving'
    assert choose_route(options,{'transport_mode':'transit'})['mode']=='transit'

def test_no_route_is_not_zero_duration():
    assert choose_route([{'mode':'walking','available':False}],{}) is None

def test_read_only_allowlist_excludes_order_mutations():
    assert not any(any(t in n.lower() for t in ('order','booktrain','cancel')) for names in ALLOW.values() for n in names)

def test_rag_provenance_and_city_filter():
    hits=retrieve('青岛','栈桥 八大关',3)
    assert hits and all(x['url'].startswith('https://') and x['fetched_at'] for x in hits)
    assert retrieve('杭州','栈桥 八大关',3)==[]

def test_planner_repairs_invalid_identity_once_without_silently_replacing(monkeypatch,tmp_path):
    import asyncio,json
    import app.planning as p
    monkeypatch.setattr(p,'RUNTIME',tmp_path)
    dt=(date.today()+timedelta(days=2)).isoformat();calls=[]
    async def fake_llm(messages,**kwargs):
        calls.append(messages)
        if len(calls)==1:d={'days':[{'date':dt,'items':[{'candidate_id':'invented','duration':60}]}]}
        elif len(calls)==2:d={'days':[{'date':dt,'items':[{'candidate_id':'spot:1','duration':60}]}]}
        else:d={'issues':[],'summary':'审核完成'}
        return {'content':json.dumps(d)},{}
    async def fake_tool(name,args):return {'items':[]}
    monkeypatch.setattr(p,'llm',fake_llm);monkeypatch.setattr(p,'local_tool',fake_tool)
    w=workspace();w['requirements'].update(days=1,adults=2);w['hotel']=None
    plan=asyncio.run(p.generate(w,lambda x:None))
    assert len(calls)==3
    assert any(e.get('candidate_id')=='spot:1' for e in plan['days'][0]['events'])
    assert 'invented' in calls[1][-1]['content']

def test_selected_return_conflict_blocks_delivery(monkeypatch,tmp_path):
    import asyncio,json
    import app.planning as p
    monkeypatch.setattr(p,'RUNTIME',tmp_path)
    dt=(date.today()+timedelta(days=2)).isoformat()
    async def fake_llm(messages,**kwargs):return {'content':json.dumps({'days':[{'date':dt,'items':[{'candidate_id':'spot:1','duration':120}]}]})},{}
    async def fake_tool(name,args):return {'items':[]}
    monkeypatch.setattr(p,'llm',fake_llm);monkeypatch.setattr(p,'local_tool',fake_tool)
    w=workspace();w['hotel']=None;w['requirements']['days']=1;w['selected_return']={'departure':dt+' 10:30'}
    with pytest.raises(Exception,match='返程冲突'):asyncio.run(p.generate(w,lambda x:None))

def test_review_handles_missing_summary_but_rejects_invalid_issues():
    from app.planning import parse_review
    assert parse_review('{"issues":["预约未确认"]}')['summary']
    assert parse_review('```json\n{"issues":[],"summary":"待确认"}\n```')['summary']=='待确认'
    with pytest.raises(ValueError):parse_review('{"issues":"没有问题"}')
    with pytest.raises(ValueError):parse_review('{"issues":[{"message":"问题"}]}')
