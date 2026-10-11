from app.travel.requirements import update_requirements
"""Verify model-visible state and validation, independent of prompt wording."""
import asyncio
import copy
import json

import pytest

from app.agents import planner as agent
from app.planning import pacing
from app import prompts
from app.integrations import providers


def trip():
    return {'requirements': {'city': '青岛', 'days': 3, 'start_date': '2026-10-12'},
            'selected_spots': [], 'catalog': {}, 'messages': []}


def test_intent_request_has_real_tools_and_optional_choice_state(monkeypatch):
    w=trip()
    async def model(messages, **kwargs):
        assert messages[0]['role']=='system' and messages[-1]['role']=='user'
        schema=kwargs['tools'][0]['function']
        assert schema['name']=='submit_intent'
        assert 'adjust_timeline' in schema['parameters']['properties']['action']['enum']
        data=json.loads(messages[-1]['content'])
        state=data['interaction_state']
        assert state['recommendation_policy']['target']==6
        assert state['arrival_time']['status']=='unknown'
        assert state['hotel']['checkin_time_confirmed_by_selection'] is False
        return {'tool_calls':[{'id':'test-intent','function':{'name':'submit_intent',
            'arguments':json.dumps({'action':'chat','patch':{},'answer':'解释',
                'mission':{'mode':'explain','objective':'解释当前安排'}})}}]},{}
    monkeypatch.setattr(agent,'llm',model)
    before=copy.deepcopy(w)
    result=asyncio.run(agent.understand({'workspace':w,'text':'为什么安排这么长？','progress':lambda _:None}))
    assert result['intent']['action']=='chat'
    assert w['requirements']==before['requirements'] and w['selected_spots']==[]


def test_provider_sends_tool_schema_separately_from_messages(monkeypatch):
    captured={}
    class Response:
        status_code=200
        def json(self):
            return {'choices':[{'message':{'role':'assistant','tool_calls':[
                {'id':'tool-1','function':{'name':'keep_timeline','arguments':'{"reason":"合理"}'}}]}}]}
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            captured.update(kwargs['json'])
            return Response()
    monkeypatch.setattr(providers,'http_client',lambda *_:Client())
    monkeypatch.setattr(providers,'record_llm_call',lambda *a,**k:None)
    monkeypatch.setattr(providers,'setting',lambda name,default=None:
        {'LLM_BASE_URL':'https://example.test/v1','LLM_API_KEY':'fixture'}.get(name,default))
    from app.planning.timeline_tools import KEEP
    messages=[{'role':'system','content':prompts.system('adjust')},
              {'role':'user','content':'查看当前安排'}]
    response,_=asyncio.run(providers.llm(messages,tools=[KEEP]))
    assert captured['messages']==messages
    assert captured['tools']==[KEEP] and captured['tool_choice']=='required'
    assert response['tool_calls'][0]['id']=='tool-1'


@pytest.mark.parametrize('days,target',[(1,2),(2,4),(3,6),(20,24)])
def test_candidate_policy_follows_the_business_target(days,target):
    w=trip();w['requirements']['days']=days
    policy=prompts.interaction_state(w)['recommendation_policy']
    assert policy['target']==target and policy['batch_size']==4
    assert policy['all_candidates_required_to_visit'] is False


def test_explicit_rest_and_recommended_arrival_are_distinct_facts():
    w=trip();w['requirements']['midday_rest_minutes']=90
    w['selected_transport']={'arrival':'2026-10-12 13:00','selection_status':'recommended'}
    state=prompts.interaction_state(w)
    assert state['rest']=={'source':'user','minutes':90,'required':True,'cancelled':False}
    assert state['arrival_time']['status']=='suggested'
    w['selected_transport']['selection_status']='confirmed'
    assert prompts.interaction_state(w)['arrival_time']['status']=='confirmed'


def test_explicit_rest_is_not_silently_cancelled_or_shortened():
    w=trip();w['requirements'].update(days=1,midday_rest_minutes=60)
    short=[{'date':'2026-10-12','events':[{'kind':'rest','rest_type':'midday','start':'13:00','end':'13:30'}]}]
    issues=pacing.required_rest_issues(w,short)
    assert issues and issues[0]['code']=='fixed_rest'
    enough=copy.deepcopy(short);enough[0]['events'][0]['end']='14:00'
    assert not pacing.required_rest_issues(w,enough)
    w['requirements'].pop('midday_rest_minutes')
    assert not pacing.required_rest_issues(w,short)


def test_new_rest_choice_replaces_old_cancellation_flag():
    w=trip();w['requirements'].update(cancel_rest=True,midday_rest_minutes=0)
    update_requirements(w,{'midday_rest_minutes':60})
    assert 'cancel_rest' not in w['requirements']
    assert prompts.interaction_state(w)['rest']['required'] is True


def test_preview_rejects_missing_user_rest_but_allows_flexible_default(monkeypatch):
    from app.planning import engine as planning
    w=trip();w['requirements'].update(days=1,day_start='16:00',day_end='20:00',midday_rest_minutes=60)
    w['catalog']={'s':{'id':'s','kind':'spot','name':'栈桥','location':'120.31,36.06'}}
    w['selected_spots']=['s']
    async def tool(*args):return {'items':[]}
    monkeypatch.setattr(planning,'local_tool',tool)
    with pytest.raises(providers.DataError) as error:
        asyncio.run(planning._generate(w,lambda _:None,preview=True))
    assert error.value.context['phase']=='schedule'
    assert any(i['code']=='fixed_rest' for i in error.value.context['issues'])
    w['requirements'].pop('midday_rest_minutes')
    result=asyncio.run(planning._generate(w,lambda _:None,preview=True))
    assert result['preview'] is True


def test_pacing_metadata_and_validation_share_limits():
    for field, limits in pacing.contract().items():
        if 'default' not in limits:continue
        assert pacing.normalize({field:limits['minimum']})[field]>=limits['minimum']
        assert pacing.normalize({field:limits['maximum']})[field]==limits['maximum']
        with pytest.raises(ValueError):pacing.normalize({field:limits['minimum']-1})
        with pytest.raises(ValueError):pacing.normalize({field:limits['maximum']+1})
