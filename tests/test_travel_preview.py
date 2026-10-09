import asyncio
import copy
import time

from app import planning,schedule,travel_preview


def trip():
    names={'h':'已选酒店','a':'上午景点','b':'下午景点一','c':'下午景点二','f':'已选午餐店'}
    catalog={cid:{'id':cid,'name':name,'kind':'hotel' if cid=='h' else 'food' if cid=='f' else 'spot','location':f'120.{300+n},36.06'} for n,(cid,name) in enumerate(names.items())}
    return {'requirements':{'city':'青岛','start_date':'2026-10-12','days':1,'day_end':'22:00'},
            'catalog':catalog,'hotel':catalog['h'],'selected_spots':['a','b','c'],
            'visit_requests':{'a':{'date':'2026-10-12','period':'morning'},'b':{'date':'2026-10-12','period':'afternoon'},'c':{'date':'2026-10-12','period':'afternoon'}},
            'meal_choices':{'2026-10-12|lunch':{'food_id':'f','mode':'chosen'}},'tickets':{}}


def test_route_preview_queries_every_leg_updates_time_and_does_not_generate_a_book(monkeypatch):
    w=trip();seen=[];before=copy.deepcopy(w['selected_spots'])
    from app import visit_analysis
    w['visit_analysis']={'signature':visit_analysis.signature(w),'status':'model','items':[
        {'candidate_id':cid,'date':'2026-10-12','period':'morning' if cid=='a' else 'afternoon','duration':duration,'reason':'明确的小范围游览','basis':'model_estimate'} for cid,duration in [('a',60),('b',45),('c',30)]],'day_pacing':[],'notices':[]}
    async def road(a,b):
        seen.append((a['id'],b['id']))
        return [{'mode':'driving','minutes':25,'available':True,'status':'available','source':{'queried_at':'2026-10-09'}}]
    async def model(*args,**kwargs):raise AssertionError('道路预览不应再次调用模型')
    monkeypatch.setattr(planning,'route_options',road);monkeypatch.setattr(planning,'llm',model)
    asyncio.run(travel_preview.refresh(w,lambda _:None))
    assert w['travel_preview']['status']=='ready'
    assert {('h','a'),('a','f'),('f','b'),('b','c')}<=set(seen)
    assert not w.get('plan') and w['selected_spots']==before
    timeline=schedule.build(w)
    legs=[r for r in timeline['entries'] if r['kind']=='route']
    assert legs and all(r['mode']=='driving' and r['route_minutes']==25 for r in legs)
    first=next(r for r in timeline['entries'] if r['candidate_id']=='a' and r['kind']=='spot')
    assert first['time']>'09:00'
    calls=len(seen);asyncio.run(travel_preview.refresh(w,lambda _:None));assert len(seen)==calls
    w['catalog']['b']['location']='120.5,36.1'
    assert travel_preview.current(w) is None


def test_missing_meal_origin_stays_pending_without_erasing_choices(monkeypatch):
    w=trip();w.pop('hotel');w['meal_choices']['2026-10-12|breakfast']={'mode':'chosen','food_id':'f'}
    async def road(*args):return []
    monkeypatch.setattr(planning,'route_options',road)
    asyncio.run(travel_preview.refresh(w,lambda _:None))
    assert w['travel_preview']['status']=='pending'
    assert w['meal_choices']['2026-10-12|breakfast']['food_id']=='f'
    assert schedule.build(w)['route_status']=='pending'


def test_explicit_route_refresh_does_not_call_model_or_change_choices(monkeypatch):
    from app import agent
    w=trip();before=copy.deepcopy(w['selected_spots'])
    async def refresh(workspace,progress):workspace['travel_preview']={'status':'ready','signature':travel_preview.signature(workspace),'expires':time.time()+900,'entries':[]}
    async def model(*args,**kwargs):raise AssertionError('只核对交通不应调用模型')
    monkeypatch.setattr(travel_preview,'refresh',refresh);monkeypatch.setattr(agent,'llm',model)
    result=asyncio.run(agent.handle(w,'refresh_routes',{},lambda _:None))
    assert '更新时间轴' in result and not w.get('plan') and w['selected_spots']==before
