import asyncio
from app import guidance,agent

def trip():
    return {'requirements':{'city':'青岛','days':3,'adults':2,'start_date':'2026-10-08'},
            'catalog':{'s1':{'id':'s1','kind':'spot','name':'栈桥'},'s2':{'id':'s2','kind':'spot','name':'八大关'},
                       'h1':{'id':'h1','kind':'hotel','name':'酒店'}},'selected_spots':['s1'],'hotel':None,'messages':[]}

def test_selected_spot_keeps_spot_scene_and_offers_user_controlled_next_step():
    w=trip();ui=guidance.describe(w,'select',{'id':'s1'})
    assert ui['view']=='spot' and ui['cta']['action']=='complete_spots'
    assert guidance.describe(w,'select',{'id':'s2'},status='loading')['status']=='loading'

def test_missing_conditions_and_day_trip_have_different_next_steps():
    w=trip();del w['requirements']['start_date']
    assert guidance.describe(w,'complete_spots')['cta']['settings']
    w=trip();w['requirements']['days']=1
    assert guidance.describe(w,'complete_spots')['view']=='transport'

def test_hotel_selection_and_return_selection_guide_following_steps():
    w=trip();w['hotel']=w['catalog']['h1']
    assert guidance.describe(w,'select',{'id':'h1'})['cta']['action']=='complete_hotel'
    w['selected_room']={'id':'r1'}
    assert guidance.describe(w,'select_room',{'id':'r1'})['cta']['action']=='complete_hotel'
    w['catalog']['t1']={'kind':'train'}
    ui=guidance.describe(w,'select',{'id':'t1'});assert ui['view']=='transport' and ui['cta']['view']=='transport'
    w.update(selected_transport={'id':'t1'},selected_return={'id':'t2'})
    assert guidance.describe(w,'select',{'id':'t1'})['cta']['action']=='plan'

def test_actual_action_overrides_model_view_and_failures_do_not_claim_results():
    w=trip()
    assert guidance.describe(w,'weather',view='hotel')['view']=='weather'
    w['ui']=guidance.describe(w,'search_hotels',status='loading')
    ui=guidance.finish(w,'failed','请先补充日期')
    assert ui['title']=='本轮未完成' and ui['message']=='请先补充日期'
    assert ui['cta']['settings'] and ui['status']=='failed'

def test_explanation_without_tool_call_still_follows_declared_topic():
    w=trip();progress=[]
    result=asyncio.run(agent.execute({'workspace':w,'intent':{'action':'chat','patch':{},'view':'hotel','answer':'住在交通方便的区域'},'progress':progress.append}))
    assert result['answer']=='住在交通方便的区域'
    assert guidance.finish(w)['view']=='hotel' and progress
