import asyncio
import copy
import json

import pytest

from app import auto_selection as auto, diagnostics, foods, schedule
from app.providers import DataError


def trip():
    return {'id':'one','requirements':{'city':'青岛','start_date':'2026-10-12','days':1},
            'catalog':{'s':{'id':'s','name':'栈桥','kind':'spot','location':'120.3,36.0'},
                       'old':{'id':'old','name':'已选餐厅','kind':'food'},
                       'new':{'id':'new','name':'新餐厅','kind':'food'}},
            'selected_spots':['s'],'meal_choices':{'2026-10-12|lunch':{'mode':'chosen','food_id':'old'}},
            'selected_transport':{'id':'t','name':'G1','selection_status':'confirmed'},
            'selected_return':{'id':'r','name':'G2','selection_status':'confirmed'}}


async def model(messages, **kwargs):
    content=json.loads(messages[1]['content'])
    return {'content':json.dumps({'ids':[content['candidates'][0]['id']],'reason':'结合当前餐次和周边位置'})},{}


def handlers(calls):
    async def handle(w, action, args, progress):
        calls.append((action,args))
        if action=='search_foods':w['food_query']={'ids':['new'],'anchor':'栈桥'}
        elif action=='meal_choice':return foods.select_meal(w,args)
        elif action=='plan':raise AssertionError('未授权生成时不能自动生成')
        else:raise AssertionError(action)
    return handle


def test_delegated_meals_become_confirmation_instead_of_undated_meal_choice():
    w=trip();intent={'action':'meal_choice','select_ids':['new']}
    value=auto.delegation(w,'其他时候的餐饮你自动帮我选一下吧',intent)
    assert value['action']=='request_auto_selection' and value['auto_categories']==['food']
    assert value['select_ids']==[] and value['auto_mode']=='remaining'
    original=copy.deepcopy(w['meal_choices']);auto.request(w,value)
    assert w['meal_choices']==original


def test_forged_or_unconfirmed_approval_never_queries_or_changes_choices():
    w=trip();calls=[];auto.request(w,{'auto_categories':['food']})
    with pytest.raises(DataError):asyncio.run(auto.run(w,{'approval_id':'forged','confirmed':True},lambda _:None,model,handlers(calls)))
    with pytest.raises(DataError):asyncio.run(auto.run(w,{'approval_id':w['pending_auto_selection']['id']},lambda _:None,model,handlers(calls)))
    assert not calls and w['meal_choices']['2026-10-12|lunch']['food_id']=='old'


def test_self_arranged_meals_and_city_discovery_do_not_request_delegated_selection():
    w=trip()
    value=auto.delegation(w,'剩余餐饮我自行安排',{'action':'meal_choice','meal_mode':'self'})
    assert value['action']=='meal_choice' and value['meal_mode']=='self'
    value=auto.delegation(w,'帮我选个城市',{'action':'discover_destinations'})
    assert value['action']=='discover_destinations'
    value=auto.delegation(w,'剩余餐饮我自己安排',{'action':'request_auto_selection'})
    assert value['action']=='chat'


def test_remaining_meals_preserve_existing_and_manual_transport():
    w=trip();calls=[];tickets=copy.deepcopy((w['selected_transport'],w['selected_return']))
    auto.request(w,{'auto_categories':['food']});pending=w['pending_auto_selection']
    asyncio.run(auto.run(w,{'approval_id':pending['id'],'confirmed':True},lambda _:None,model,handlers(calls)))
    assert w['meal_choices']['2026-10-12|lunch']['food_id']=='old'
    assert w['meal_choices']['2026-10-12|dinner']['food_id']=='new'
    assert (w['selected_transport'],w['selected_return'])==tickets
    assert all(a not in ('train','flight','select') for a,_ in calls)


def test_replace_mode_is_explicit_and_replaces_each_meal():
    w=trip();calls=[];auto.request(w,{'auto_categories':['food'],'auto_mode':'replace'})
    asyncio.run(auto.run(w,{'approval_id':w['pending_auto_selection']['id'],'confirmed':True},lambda _:None,model,handlers(calls)))
    assert w['meal_choices']['2026-10-12|lunch']['food_id']=='new'
    assert any(args['meal_period']=='lunch' for action,args in calls if action=='meal_choice')


def test_changed_conditions_invalidate_consent():
    w=trip();auto.request(w,{'auto_categories':['food']});pending=w['pending_auto_selection']
    w['requirements']['days']=2
    with pytest.raises(DataError,match='已经变化'):asyncio.run(auto.run(w,{'approval_id':pending['id'],'confirmed':True},lambda _:None,model,handlers([])))


def test_automatic_ticket_request_remains_a_query_and_explicit_named_choice_is_allowed():
    w=trip();w['catalog']['t']=w['selected_transport']|{'kind':'train'}
    v=auto.delegation(w,'车票你自动帮我选一下',{'action':'train','select_ids':['t']})
    assert v['action']=='train' and v['auto_select'] is False and not v['select_ids']
    v=auto.delegation(w,'帮我选G1',{'action':'chat','select_ids':['t']})
    assert v['select_ids']==['t']


def test_cancel_keeps_saved_choices():
    w=trip();before=copy.deepcopy(w);auto.request(w,{'auto_categories':['food']});auto.cancel(w)
    assert 'pending_auto_selection' not in w and w['meal_choices']==before['meal_choices']


def test_bad_model_proposal_does_not_blame_the_users_valid_selections():
    w=trip();message,context=diagnostics.proposal(w,['遗漏ID：s'],[],{'s'},['2026-10-12'])
    assert context['model_output_error'] and '无需因此修改' in context['issues'][0]['message']
    assert '栈桥' in context['issues'][0]['message'] and context['issues'][0]['retry']


def test_date_and_capacity_problems_identify_real_places_and_dates():
    w=trip();w['visit_requests']={'s':{'date':'2026-10-14','period':'morning'}}
    issues=diagnostics.invalid_dates(w,['s'],['2026-10-12'])
    assert issues[0]['candidate_ids']==['s'] and '2026-10-14' in issues[0]['message'] and issues[0]['settings']
    w['visit_requests']={}
    message,c=diagnostics.proposal(w,['容量不足'],[{'date':'2026-10-12','items':[{'candidate_id':'s','duration':600}]}],{'s'},['2026-10-12'])
    assert c['issues'][0]['code']=='day_capacity' and '栈桥' in c['issues'][0]['message']
    assert not c['issues'][0].get('direction'), '普通每日负担不能误称返程冲突'


def test_failed_meal_query_preserves_previously_selected_meal():
    w=trip();auto.request(w,{'auto_categories':['food'],'auto_mode':'replace'})
    async def fail(*args):raise DataError('当前区域暂未查到餐厅')
    text=asyncio.run(auto.run(w,{'approval_id':w['pending_auto_selection']['id'],'confirmed':True},lambda _:None,model,fail))
    assert w['meal_choices']['2026-10-12|lunch']['food_id']=='old' and '未完成' in text


def test_long_meal_selection_continues_under_same_consent_and_replay_is_rejected():
    w=trip();w['requirements']['days']=4;calls=[]
    auto.request(w,{'auto_categories':['food']});id=w['pending_auto_selection']['id']
    asyncio.run(auto.run(w,{'approval_id':id,'confirmed':True},lambda _:None,model,handlers(calls)))
    assert w['auto_selection_run']['meal_cursor']==8
    w['revision']=20  # Job bookkeeping must not invalidate the user's unchanged travel scope.
    asyncio.run(auto.run(w,{'approval_id':id},lambda _:None,model,handlers(calls),continuing=True))
    assert 'auto_selection_run' not in w and len(w['meal_choices'])==12
    with pytest.raises(DataError):asyncio.run(auto.run(w,{'approval_id':id,'confirmed':True},lambda _:None,model,handlers(calls)))


def test_generation_waits_for_users_transport_confirmation():
    w=trip();w['selected_return']['selection_status']='recommended';calls=[]
    auto.request(w,{'auto_categories':['food']})
    text=asyncio.run(auto.run(w,{'approval_id':w['pending_auto_selection']['id'],'confirmed':True,'generate_plan':True},lambda _:None,model,handlers(calls)))
    assert '手动选定车票或机票' in text and not any(a=='plan' for a,_ in calls)
