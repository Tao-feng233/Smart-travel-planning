import asyncio
import copy
import json

import pytest

from app import agent, auto_selection, guidance, journey, planning, report


def trip():
    h={'id':'h','name':'位置已选酒店','kind':'hotel','location':'120.30,36.05','price':200,'address':'青岛测试地址'}
    return {'id':'optional-room','requirements':{'city':'青岛','origin':'青岛','start_date':'2026-10-12','days':2,'adults':2},
            'catalog':{'h':h,'s':{'id':'s','name':'景点','kind':'spot','location':'120.31,36.05'}},
            'selected_spots':['s'],'spots_confirmed':True,'hotel':copy.deepcopy(h),'selected_room':None,'messages':[]}


def test_complete_hotel_without_room_does_not_fetch_or_select_rates(monkeypatch):
    w=trip()
    async def forbidden(*args,**kwargs):pytest.fail('完成住宿不应查询房型或报价')
    monkeypatch.setattr(agent,'tuniu',forbidden)
    answer=asyncio.run(agent.handle(w,'complete_hotel',{},lambda _:None))
    assert w['hotel']['id']=='h' and w['selected_room'] is None
    assert w['ui']['view']=='food' and '餐饮安排' in answer and '下一步：' not in answer


def test_next_step_and_guidance_accept_hotel_location_without_room():
    w=trip()
    assert journey.next_step(w)['view']=='food'
    ui=guidance.describe(w,'select',{'id':'h'})
    assert ui['cta']['action']=='complete_hotel'


def test_remaining_auto_selection_keeps_hotel_without_adding_room():
    w=trip();before=copy.deepcopy(w['hotel'])
    auto_selection.request(w,{'auto_categories':['hotel']})
    async def forbidden(*args,**kwargs):pytest.fail('补齐模式应保留已有酒店，不补选房型')
    asyncio.run(auto_selection.run(w,{'approval_id':w['pending_auto_selection']['id'],'confirmed':True},lambda _:None,forbidden,forbidden))
    assert w['hotel']==before and w['selected_room'] is None


def test_auto_hotel_selection_does_not_depend_on_room_provider():
    w=trip();w['hotel']=None;calls=[]
    auto_selection.request(w,{'auto_categories':['hotel']})
    async def model(*args,**kwargs):return {'content':json.dumps({'ids':['h'],'reason':'靠近游览区域'})},{}
    async def handle(workspace,action,args,progress):
        calls.append(action)
        if action=='search_hotels':workspace['hotel_query']={'ids':['h']};return '候选已查询'
        if action=='select':return await agent.handle(workspace,action,args,progress)
        pytest.fail('自动住宿不应依赖房型查询或选择：'+action)
    asyncio.run(auto_selection.run(w,{'approval_id':w['pending_auto_selection']['id'],'confirmed':True},lambda _:None,model,handle))
    assert calls==['search_hotels','select'] and w['hotel']['id']=='h' and w['selected_room'] is None


def test_invalid_hotel_location_still_requires_refresh():
    w=trip();w['hotel']['location_stale']=True
    with pytest.raises(agent.DataError,match='有效住宿'):
        asyncio.run(agent.handle(w,'complete_hotel',{},lambda _:None))


def test_plan_uses_hotel_as_route_anchor_without_room(monkeypatch,tmp_path):
    w=trip();monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    source={'name':'合成来源','queried_at':'2026-10-08'}
    for item in w['catalog'].values():item['source']=source
    w['hotel']['source']=source;w['revision']=1
    async def model(messages,**kwargs):
        value={'issues':[],'summary':'待核实费用'} if kwargs.get('label')=='review' else {
            'days':[{'date':'2026-10-12','items':[{'candidate_id':'s','duration':60}]}]}
        return {'content':json.dumps(value)},{}
    async def tool(*args):return {'items':[]}
    async def routes(a,b):return [{'mode':'walking','available':True,'status':'available','minutes':5,'source':source}]
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'route_options',routes)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    assert plan['selected_room'] is None
    assert any(e.get('kind')=='route' and '位置已选酒店' in e['name'] for d in plan['days'] for e in d['events'])
    assert plan['budget']['hotel_reference']==400
    assert any('具体房型' in item for item in plan['budget']['unknown'])
    w['plan']=plan
    assert '具体房型：未选择（可选）' in report.markdown(w)
