import asyncio
import json

import pytest

from app import agent,auto_selection,replies,goal_agent


def trip():
    return {'id':'goal-trip','requirements':{'city':'青岛','start_date':'2026-10-12','days':3},
            'catalog':{},'selected_spots':[],'messages':[]}


def call(name,args):
    return {'tool_calls':[{'id':'call-'+name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},{}


@pytest.mark.parametrize('text',[
    '直接给我在合理的情况下随机生成一份旅游计划',
    '我不想一个一个挑，给我一份能参考的方案',
    '余下的细节交给你处理，已有的别动',
    '按我的要求把整趟安排妥当',
])
def test_semantic_delegation_is_not_overridden_by_destination_discovery(text):
    intent={'action':'discover_destinations','patch':{},'mission':{'mode':'delegate','objective':'完成旅行安排','scopes':['spots','hotel','food'],'multi_step':True,'generate_plan':True}}
    value=auto_selection.delegation(trip(),text,intent)
    assert value['action']=='request_auto_selection' and not value['select_ids']
    assert value['auto_generate_plan']


def test_agent_uses_real_tool_observation_to_choose_the_next_step(monkeypatch):
    w=trip();calls=[];messages_seen=[]
    async def model(messages,**kwargs):
        messages_seen.append(messages)
        if len(messages_seen)==1:return call('submit_intent',{'action':'weather','patch':{},'answer':'核对天气与用餐','mission':{'mode':'query','objective':'查看天气并查询附近餐厅','scopes':['food'],'multi_step':True}})
        if len(messages_seen)==2:return call('search_foods',{'keywords':['当地餐厅']})
        return call('finish_request',{'answer':'已核对天气并找到附近餐厅。','status':'completed'})
    async def handle(workspace,action,args,progress):
        calls.append(action)
        if action=='weather':workspace['weather']={'days':[{'date':'2026-10-12','text':'晴'}]}
        if action=='search_foods':workspace['food_query']={'ids':[]}
        return action+'查询已执行'
    async def weather(*args):pass
    monkeypatch.setattr(agent,'llm',model);monkeypatch.setattr(agent,'handle',handle);monkeypatch.setattr(agent,'ensure_weather',weather)
    token=replies.SINK.set(None)
    try:answer=asyncio.run(agent.run_chat(w,'顺便核对天气，再找周围吃饭的地方',lambda _:None))
    finally:replies.SINK.reset(token)
    assert calls==['weather','search_foods']
    assert any(m.get('role')=='tool' and 'weather' in m.get('content','') for m in messages_seen[1])
    assert w['assistant_goal']['status']=='completed' and '附近餐厅' in answer


def test_goal_status_is_persisted_for_single_step_and_confirmation():
    w=trip();goal=goal_agent.start(w,{'mission':{'mode':'delegate','objective':'补齐餐饮'}})
    goal['status']='awaiting_confirmation'
    assert w['assistant_goal']['status']=='awaiting_confirmation'


def test_consultation_cannot_destroy_existing_trip_or_schedule():
    w=trip();w['selected_spots']=['saved'];w['selected_return']={'id':'return'}
    intent={'action':'plan','patch':{'city':'杭州'},'select_ids':['new'],
            'mission':{'mode':'consult','objective':'比较杭州与当前旅行'}}
    value=goal_agent.normalize(w,'看看杭州和现在的方案有什么区别',intent)
    assert value['action']=='chat' and value['patch']=={}
    assert 'select_ids' not in value
    assert w['selected_spots']==['saved'] and w['selected_return']['id']=='return'


def test_missing_conditions_are_only_proposed_until_confirmation():
    w=trip();w['requirements']={};before=json.dumps(w['requirements'])
    auto_selection.request(w,{'allow_missing':True,'auto_categories':['destination','spots'],'auto_generate_plan':True})
    assert json.dumps(w['requirements'])==before and not w['selected_spots']
    pending=w['pending_auto_selection']
    assert pending['generate_plan_default'] and pending['proposed_requirements']['days']==3
    assert pending['proposed_requirements']['start_date']


def test_read_loop_rejects_selection_and_stops_repeated_invalid_calls():
    w=trip();w['selected_spots']=['saved'];goal_agent.start(w,{'mission':{'mode':'query','objective':'查询资料'}})
    first=goal_agent.observation(w,'weather',{},'天气已查询');calls=[];decisions=[]
    async def model(*args,**kwargs):decisions.append(True);return call('select',{'id':'other'})
    async def handle(*args):calls.append(True)
    result=asyncio.run(goal_agent.continue_goal(w,first,model,handle,lambda _:None))
    assert not calls and len(decisions)==2 and w['selected_spots']==['saved']
    assert w['assistant_goal']['status']=='partial' and '尚未完成' in result


def test_delegated_defaults_require_actual_user_text_evidence():
    w=trip();intent={'action':'request_auto_selection','patch':{'city':'青岛','days':5,'adults':2},
        'patch_evidence':{'city':'青岛','days':'游玩5天'},'mission':{'mode':'delegate','objective':'安排旅行'}}
    value=goal_agent.normalize(w,'帮我安排青岛游玩5天',intent)
    assert value['patch']=={} and value['proposed_patch']=={'city':'青岛','days':5}
    auto_selection.request(w,{**value,'allow_missing':True})
    assert w['requirements']['days']==3
    assert w['pending_auto_selection']['proposed_requirements']['days']==5


def test_explanation_about_optimization_does_not_execute_keyword_repair(monkeypatch):
    w=trip();w['plan']={'title':'已有计划','days':[]};calls=[]
    async def model(*args,**kwargs):return call('submit_intent',{'action':'chat','patch':{},'answer':'优化会核对时段与路线。','mission':{'mode':'explain','objective':'说明优化方式','multi_step':False}})
    async def handle(workspace,action,args,progress):calls.append(action);return ''
    monkeypatch.setattr(agent,'llm',model);monkeypatch.setattr(agent,'handle',handle)
    token=replies.SINK.set(None)
    try:asyncio.run(agent.run_chat(w,'这个优化会怎么修正计划，先解释一下',lambda _:None))
    finally:replies.SINK.reset(token)
    assert calls==['chat'] and w['plan']['title']=='已有计划'
