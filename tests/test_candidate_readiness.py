import asyncio
import copy
import pytest
from app import agent,providers,journey,planning,locations


def trip():
    return {'requirements':{'city':'青岛','origin':'济南','start_date':'2026-10-12','days':1,'adults':1},'catalog':{},'selected_spots':[]}


def test_unlocated_supplier_hotels_are_not_published(monkeypatch):
    w=trip()
    async def vendor(*_):return {'data':{'hotels':[{'hotelId':x,'hotelName':x} for x in ('verified','missing')]},'source':{}}
    async def tool(name,args):return {'items':[{'name':'verified','location':'120.3,36.05','provider_id':'h','source':{}}]} if args.get('keywords')=='verified' else {'items':[]}
    async def recommend(w,items,*_):
        assert all(locations.coordinate(p.get('location')) for p in items)
        return '候选'
    monkeypatch.setattr(agent,'tuniu',vendor);monkeypatch.setattr(agent,'local_tool',tool);monkeypatch.setattr(agent,'recommend',recommend)
    asyncio.run(agent.search_hotels_by_keyword(w,{'keyword':'hotel'},lambda _:None,recommend))
    assert [p['name'] for p in w['candidates']]==['verified']
    assert w['hotel_query']['excluded'][0]['name']=='missing'


def test_self_drive_skips_ticket_gate_and_keeps_other_choices(monkeypatch):
    w=trip();w.update(selected_spots=['a'],spots_confirmed=True,stay_skipped=True,dining_reviewed=True,hotel=None)
    w['selected_transport']={'id':'old','selection_status':'confirmed'};w['plan']={'stale':False}
    async def forbidden(*_):pytest.fail('Self-drive cannot query tickets')
    monkeypatch.setattr(agent,'tuniu',forbidden)
    asyncio.run(agent.handle(w,'transport_arrangement',{'mode':'self_drive'},lambda _:None))
    assert w['requirements']['intercity_mode']=='self_drive' and w['requirements']['transport_mode']=='driving'
    assert w['selected_transport'] is None and w['selected_spots']==['a'] and w['plan']['stale']
    assert journey.next_step(w)['view']=='plan'
    asyncio.run(agent.handle(w,'complete_hotel',{},lambda _:None)) if w.get('hotel') else None
    assert planning.choose_route([{'mode':'walking','available':True,'minutes':10},{'mode':'driving','available':True,'minutes':5}],w['requirements'])['mode']=='driving'


def test_coordinate_readiness_repairs_poi_by_id_and_excludes_ambiguous():
    items=[{'id':'amap:a','kind':'spot','name':'a','location':None},{'id':'b','kind':'hotel','name':'b','location':'120.3,36.05','location_status':'ambiguous'}]
    async def tool(name,args):
        assert name=='get_place_details' and args['ids']==['amap:a']
        return {'items':[{'id':'amap:a','name':'a','location':'120.35,36.06','citycode':'0532','source':{}}]}
    ready,excluded=asyncio.run(locations.ready_candidates(trip(),copy.deepcopy(items),tool))
    assert [p['id'] for p in ready]==['amap:a'] and excluded[0]['id']=='b'


def test_route_prices_and_transit_stations_survive_normalization(monkeypatch):
    async def amap(path,args,*_):
        if path.endswith('driving'):return {'data':{'route':{'taxi_cost':'25.6','paths':[{'cost':{'duration':'1200','tolls':'0'},'distance':'5000'}]}},'source':{}}
        return {'data':{'route':{'transits':[{'cost':{'duration':'2400'},'distance':'6000','segments':[
            {'cost':{'transit_fee':'2'},'bus':{'buslines':[{'name':'地铁3号线','departure_stop':{'name':'青岛站'},'arrival_stop':{'name':'五四广场'},'via_num':'7'},{'name':'不应同时乘坐的备选'}]}},
            {'cost':{'transit_fee':'2'},'bus':{'buslines':[{'name':'地铁2号线','departure_stop':{'name':'五四广场'},'arrival_stop':{'name':'浮山所'}}]}}]}]}},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    rt=asyncio.run(providers.route('120.3,36.05','120.35,36.06','driving'))
    assert rt['taxi_cost']==25.6 and rt['tolls']==0
    rt=asyncio.run(providers.route('120.3,36.05','120.35,36.06','transit','0532'))
    assert rt['fare']==4 and rt['details']==['地铁3号线','地铁2号线']
    assert rt['steps'][0]['from']=='青岛站' and rt['steps'][1]['to']=='浮山所'


def test_unknown_route_price_is_not_zero(monkeypatch):
    async def amap(*_):return {'data':{'route':{'paths':[{'cost':{'duration':'600'},'distance':'1000'}]}},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    assert asyncio.run(providers.route('120.3,36.05','120.35,36.06','driving'))['taxi_cost'] is None


def test_export_has_prices_and_transfer_instructions():
    from app.report import route_lines
    lines=route_lines({'mode':'transit','fare':4,'steps':[{'instruction':'乘坐 地铁3号线','from':'青岛站','to':'五四广场'},{'instruction':'乘坐 地铁2号线','from':'五四广场','to':'浮山所'}]})
    assert '参考 ¥4' in '\n'.join(lines) and '五四广场 上车' in '\n'.join(lines)
    assert '预估 ¥25' in '\n'.join(route_lines({'mode':'driving','taxi_cost':25}))
    assert '停车费待核实' in '\n'.join(route_lines({'mode':'driving','taxi_cost':25,'tolls':0},True))
