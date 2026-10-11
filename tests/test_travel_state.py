import asyncio
import copy
import json
from datetime import date, timedelta

import pytest

from app.agents import planner as agent, replies
from app.travel import choices, stay_plan
from app.travel.requirements import update_requirements
from app.travel.selections import remove_selection


def trip():
    start=date.today()+timedelta(days=10)
    day=start.isoformat();back=(start+timedelta(days=3)).isoformat()
    outbound={'id':'out','kind':'train','direction':'outbound','departure':day+' 08:00',
              'arrival':day+' 10:00','selection_status':'confirmed'}
    returning={'id':'back','kind':'train','direction':'return','departure':back+' 18:00',
               'arrival':back+' 20:00','selection_status':'confirmed'}
    hotel={'id':'h','kind':'hotel','name':'合成酒店','location':'120.31,36.06'}
    other={'id':'other','kind':'hotel','name':'另一酒店','location':'120.32,36.06'}
    return {'id':'state-fixture','requirements':{'city':'青岛','origin':'郑州','start_date':day,
            'days':3,'adults':2,'children':0,'rooms':1,'return_date':back,'preferences':['海滨']},
            'catalog':{'out':copy.deepcopy(outbound),'back':copy.deepcopy(returning),'h':hotel,'other':other},
            'selected_transport':outbound,'selected_return':returning,'hotel':copy.deepcopy(hotel),
            'stay_hotels':{day:'h',(start+timedelta(days=1)).isoformat():'other'},
            'selected_room':{'id':'room','hotel_id':'h'},
            'selected_rooms':{'h':{'id':'room','hotel_id':'h'},'other':{'id':'other-room','hotel_id':'other'}},
            'selected_spots':[],'messages':[],'tickets':{},'meal_choices':{},'ui':{},'trace':[],
            'plan':{'stale':False}}


@pytest.mark.parametrize('patch',[{'days':2},{'rooms':2},{'adults':3},{'children':1,'child_ages':[5]}])
def test_lodging_or_party_changes_keep_confirmed_tickets(patch):
    w=trip();before=copy.deepcopy(w)
    update_requirements(w,patch)
    assert w['selected_transport']==before['selected_transport']
    assert w['selected_return']==before['selected_return']
    assert not w['catalog']['out'].get('stale')
    assert w['hotel']['quote_stale'] and w['hotel']['id']=='h'
    assert w['selected_room'] is None and w['plan']['stale']


@pytest.mark.parametrize('direction',['outbound','return'])
@pytest.mark.parametrize('result',['success','empty','failure'])
def test_alternative_ticket_query_never_commits_formal_dates(monkeypatch,direction,result):
    w=trip();before=copy.deepcopy(w)
    query_day=(date.today()+timedelta(days=12)).isoformat();seen=[]

    async def provider(service,name,args):
        seen.append(args)
        if result=='failure':raise agent.DataError('合成接口失败')
        rows=[] if result=='empty' else [{'trainNum':'G999','departureTime':query_day+' 12:00',
              'arrivalTime':query_day+' 14:00','seats':[] }]
        return {'data':{'data':rows},'source':{'name':'合成来源'}}

    monkeypatch.setattr(agent,'tuniu',provider)
    if result=='failure':
        with pytest.raises(agent.DataError):
            asyncio.run(agent.handle(w,'train',{'direction':direction,'departure_date':query_day},lambda _:None))
    else:
        asyncio.run(agent.handle(w,'train',{'direction':direction,'departure_date':query_day},lambda _:None))
    assert seen[0]['departureDate']==query_day
    assert w['requirements']==before['requirements']
    assert w['selected_transport']==before['selected_transport']
    assert w['selected_return']==before['selected_return']
    assert w['plan']==before['plan']


def test_selecting_alternative_ticket_commits_only_its_direction():
    w=trip();outbound=copy.deepcopy(w['selected_transport'])
    day=(date.today()+timedelta(days=12)).isoformat()
    candidate={'id':'new','kind':'train','direction':'return','name':'G999','departure':day+' 18:00',
               'arrival':day+' 20:00','query_conditions':{'departureDate':day}}
    w['catalog']['new']=candidate
    w['transport_queries']={'train:return':{'query_conditions':{'departureDate':day},'items':[candidate]}}
    choices.transport_select(w,candidate,replace=True)
    assert w['requirements']['return_date']==day
    assert w['selected_return']['id']=='new'
    assert w['selected_transport']==outbound
    assert not w['selected_return'].get('stale')
    assert 'train:return' in w['transport_queries']


def test_explicit_date_change_invalidates_only_mismatching_direction():
    w=trip();outbound=copy.deepcopy(w['selected_transport'])
    update_requirements(w,{'return_date':(date.today()+timedelta(days=14)).isoformat()})
    assert w['selected_return'] is None
    assert w['selected_transport']==outbound


def test_selecting_legacy_dated_candidate_does_not_make_it_stale():
    w=trip();day=(date.today()+timedelta(days=12)).isoformat()
    candidate={'id':'legacy','kind':'train','direction':'return','departure':day+' 18:00','arrival':day+' 20:00'}
    w['catalog']['legacy']=candidate
    choices.transport_select(w,candidate,replace=True)
    assert w['requirements']['return_date']==day
    assert not w['selected_return'].get('stale')


def test_hotel_removal_clears_associated_nights_and_rooms_only():
    w=trip();day=w['requirements']['start_date']
    assert remove_selection(w,'h')
    assert w['hotel'] is None and w['selected_room'] is None
    assert day not in w['stay_hotels'] and 'h' not in w['selected_rooms']
    assert stay_plan.hotel_for(w,day) is None
    assert list(w['stay_hotels'].values())==['other']
    assert list(w['selected_rooms'].values())[0]['hotel_id']=='other'
    assert w['catalog']['h']['id']=='h'  # Factual candidate data remains available.
    assert w['plan']['stale']


def test_removing_non_primary_hotel_also_clears_its_assignment():
    w=trip();main=copy.deepcopy(w['hotel'])
    remove_selection(w,'other')
    assert w['hotel']==main and list(w['stay_hotels'].values())==['h']


@pytest.mark.parametrize('mode,values,expected',[
    ('add',['人文'],['海滨','人文']),('replace',['人文'],['人文']),
    ('remove',['海滨'],[]),('replace',[],[])])
def test_preference_operations(mode,values,expected):
    w=trip()
    update_requirements(w,{},preference_updates={'preferences':{'mode':mode,'values':values}})
    assert w['requirements']['preferences']==expected
    assert w['selected_return']['id']=='back'


def test_invalid_preference_operation_is_atomic():
    w=trip();before=copy.deepcopy(w)
    with pytest.raises(agent.DataError):
        update_requirements(w,{'rooms':2},preference_updates={'preferences':{'mode':'invalid','values':['人文']}})
    assert w==before


def test_conversation_uses_shared_preference_and_removal_services(monkeypatch):
    w=trip()
    async def handle(*args):return '合成完成'
    monkeypatch.setattr(agent,'handle',handle)
    intent={'action':'chat','patch':{},'remove_ids':['h'],
            'preference_updates':{'preferences':{'mode':'replace','values':['人文']}},
            'mission':{'mode':'act','objective':'取消酒店并更换偏好','scopes':['hotel','spots'],'multi_step':False}}
    token=replies.SINK.set(None)
    try:asyncio.run(agent.execute({'workspace':w,'intent':intent,'text':'取消酒店，改成人文偏好','progress':lambda _:None}))
    finally:replies.SINK.reset(token)
    assert w['requirements']['preferences']==['人文']
    assert stay_plan.hotel_for(w,w['requirements']['start_date']) is None
    assert w['selected_return']['id']=='back'


def test_native_intent_to_ticket_query_preserves_formal_trip(monkeypatch):
    w=trip();before=copy.deepcopy(w);day=(date.today()+timedelta(days=12)).isoformat()
    async def model(messages,**kwargs):
        properties=kwargs['tools'][0]['function']['parameters']['properties']
        assert '查询不修改正式日期' in properties['departure_date']['description']
        intent={'action':'train','patch':{},'direction':'return','departure_date':day,'answer':'查询另一日班次',
                'mission':{'mode':'query','objective':'比较其他返程日期','scopes':['transport'],'multi_step':False}}
        return {'tool_calls':[{'id':'q','type':'function','function':{'name':'submit_intent','arguments':json.dumps(intent)}}]},{}
    async def provider(*args):return {'data':{'data':[]},'source':{'name':'合成来源'}}
    monkeypatch.setattr(agent,'llm',model);monkeypatch.setattr(agent,'tuniu',provider)
    token=replies.SINK.set(None)
    try:asyncio.run(agent.run_chat(w,'只比较一下另一日返程票',lambda _:None))
    finally:replies.SINK.reset(token)
    assert w['requirements']==before['requirements']
    assert w['selected_return']==before['selected_return']
    assert w['plan']==before['plan']


def test_explanation_does_not_apply_preference_edits(monkeypatch):
    w=trip();before=copy.deepcopy(w)
    async def handle(*args):return '合成解释'
    monkeypatch.setattr(agent,'handle',handle)
    intent={'action':'chat','patch':{},'preference_updates':{'preferences':{'mode':'replace','values':[]}},
            'mission':{'mode':'explain','objective':'解释偏好设置','scopes':['spots'],'multi_step':False}}
    token=replies.SINK.set(None)
    try:asyncio.run(agent.execute({'workspace':w,'intent':intent,'text':'解释当前偏好','progress':lambda _:None}))
    finally:replies.SINK.reset(token)
    assert w['requirements']==before['requirements']
