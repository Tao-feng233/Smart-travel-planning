import asyncio
import json

from app import agent,replies


def trip():
    return {'id':'recommendation-fixture','requirements':{'city':'青岛','days':3},
            'catalog':{},'selected_spots':[],'messages':[],'tickets':{}}


def test_first_city_request_asks_preferences_before_any_search(monkeypatch):
    w=trip();calls=[]
    async def handle(*args):calls.append(args[1]);return '已查询'
    monkeypatch.setattr(agent,'handle',handle)
    intent={'action':'search_spots','patch':{'budget':2000},'answer':'查询青岛景点',
            'mission':{'mode':'consult','objective':'推荐青岛景点','scopes':['spots'],'multi_step':False}}
    token=replies.SINK.set(None)
    try:answer=asyncio.run(agent.execute({'workspace':w,'text':'我想去青岛玩，预算2k，大概3天','intent':intent,'progress':lambda _:None}))['answer']
    finally:replies.SINK.reset(token)
    assert not calls
    assert '偏好' in answer and '暂无偏好' in answer
    assert w['spot_preference']['status']=='awaiting'


def test_recommendation_gets_party_and_only_applicable_weather(monkeypatch):
    w=trip();w['requirements'].update(start_date='2026-10-12',adults=3,children=1,child_ages=[5],companion_notes=['有一位老人，减少爬坡'])
    w['weather_for']=['青岛','2026-10-12',3]
    w['weather']={'source':{'name':'天气来源'},'days':[{'date':'2026-10-09','text':'晴'},{'date':'2026-10-12','text':'雨'}]}
    seen=[]
    async def model(messages,**kwargs):seen.append(json.loads(messages[-1]['content']));return {'content':'{"recommendations":[],"summary":"建议"}'},{}
    monkeypatch.setattr(agent,'llm',model)
    monkeypatch.setattr('app.storage.cached',lambda _:None)
    monkeypatch.setattr('app.storage.put_cache',lambda *args:None)
    asyncio.run(agent.recommend(w,[{'id':'s','name':'景点','kind':'spot'}],'推荐景点'))
    context=seen[0]['recommendation_context']
    assert context['party']['children']==1 and context['party']['companion_notes']==['有一位老人，减少爬坡']
    assert [row['date'] for row in context['weather']['days']]==['2026-10-12']
    assert context['weather']['uncovered_dates']==['2026-10-13','2026-10-14']


def test_default_and_known_preferences_do_not_block_and_do_not_repeat():
    from app.recommendation_context import needs_preferences,ask,context
    w=trip();ask(w)
    assert not needs_preferences(w,{'preference_mode':'default'})
    assert not needs_preferences(w,{})
    w['requirements']['city']='杭州'
    assert needs_preferences(w,{})
    w['requirements']['preferences']=['自然风光']
    assert not needs_preferences(w,{})
    w['weather_for']=['青岛','2026-10-12',3]
    w['weather']={'days':[{'date':'2026-10-12','text':'雨'}]}
    w['requirements']['start_date']='2026-10-12'
    assert context(w)['weather']['status']=='unknown'
