import asyncio
import json

from app import planning,schedule,transport_links


def trip():
    return {'requirements':{'city':'青岛','start_date':'2026-10-12','days':1},
        'hotel':{'id':'h','kind':'hotel','name':'酒店','location':'120.3,36.06'},
        'selected_transport':{'id':'train','kind':'train','arrival_station':'青岛北','arrival':'2026-10-12 08:00'},
        'selected_return':{'id':'flight','kind':'flight','departure_station':'青岛胶东国际机场','departure':'2026-10-13 11:00'}}


def test_unique_verified_station_and_airport_routes_extend_time_windows():
    w=trip();calls=[]
    async def tool(name,args):
        calls.append(name)
        return {'items':[{'id':args['kind'],'name':'青岛北站' if args['kind']=='station' else '青岛胶东国际机场','location':'120.2,36.1','endpoint_scope':'primary'}]}
    async def roads(*args):return [{'mode':'driving','available':True,'status':'available','minutes':100,'source':{'queried_at':'2026-10-09'}}]
    asyncio.run(transport_links.resolve(w,lambda _:None,tool,roads,planning.choose_route))
    assert transport_links.offset(w,'outbound')==145
    assert transport_links.offset(w,'return')==250
    assert schedule.windows(w,'2026-10-12')[0]==8*60+145
    assert schedule.windows(w,'2026-10-13')[1]==11*60-250
    arrival=transport_links.events(w,'outbound',480)
    assert any(e['kind']=='route' and e['route']['minutes']==100 for e in arrival)
    returned=transport_links.events(w,'return',660)
    assert returned[-1]['end']=='11:00'
    assert schedule.minutes(returned[-1]['end'])-schedule.minutes(returned[-1]['start'])>=120
    before=len(calls);asyncio.run(transport_links.resolve(w,lambda _:None,tool,roads,planning.choose_route));assert len(calls)==before
    w['hotel']['location']='120.4,36.07'
    assert transport_links.current(w) is None


def test_ambiguous_transport_poi_keeps_transfer_unknown():
    w=trip()
    async def tool(name,args):return {'items':[{'id':str(i),'name':'青岛北站','location':'120.2,36.1','endpoint_scope':'primary'} for i in range(2)]}
    async def roads(*args):raise AssertionError('不能替用户猜测站点')
    asyncio.run(transport_links.resolve(w,lambda _:None,tool,roads,planning.choose_route))
    assert w['transport_links']['links']['outbound']['status']=='unknown'
    assert transport_links.offset(w,'outbound')==90


def test_cross_midnight_transfer_is_not_fabricated_within_a_single_day():
    w=trip()
    async def tool(name,args):return {'items':[{'id':args['kind'],'name':args['keywords']+'站' if args['kind']=='station' else args['keywords'],'location':'120.2,36.1','endpoint_scope':'primary'}]}
    async def roads(*args):return [{'mode':'driving','available':True,'minutes':100}]
    asyncio.run(transport_links.resolve(w,lambda _:None,tool,roads,planning.choose_route))
    assert transport_links.events(w,'outbound',23*60)==[]
    assert transport_links.events(w,'return',2*60)==[]


def test_generated_book_includes_arrival_and_return_driving_links(monkeypatch,tmp_path):
    w=trip();w['requirements']['day_end']='22:00';w['selected_spots']=['s'];w['catalog']={'s':{'id':'s','name':'游览地点','kind':'spot','location':'120.31,36.07'}}
    async def tool(name,args):
        if name=='retrieve_guides':return {'items':[]}
        return {'items':[{'id':args['kind'],'name':'青岛北站' if args['kind']=='station' else '青岛胶东国际机场','location':'120.2,36.1','endpoint_scope':'primary'}]}
    async def road(*args):return [{'mode':'driving','available':True,'status':'available','minutes':25,'source':{'queried_at':'2026-10-09'}}]
    async def model(*args,**kwargs):return {'content':json.dumps({'issues':[],'summary':'建议'} if kwargs.get('label')=='review' else {'days':[{'date':'2026-10-12','items':[{'candidate_id':'s','duration':60}]}]})},{}
    monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'route_options',road);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    assert any(e.get('route_scope')=='arrival_transfer' for d in plan['days'] for e in d['events'])
    assert any(e.get('route_scope')=='return_transfer' for d in plan['days'] for e in d['events'])
