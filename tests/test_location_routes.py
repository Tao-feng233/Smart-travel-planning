import asyncio
import pytest
from app import agent, planning, providers


def test_all_hotel_candidates_receive_map_address_and_coordinates(monkeypatch):
    w={'requirements':{'city':'成都','start_date':'2026-10-20','days':3,'adults':1},
       'catalog':{},'selected_spots':[]}
    async def vendor(*args):
        return {'data':{'hotels':[{'hotelId':str(i),'hotelName':f'全季酒店（成都示例{i}店）'} for i in range(4)]},'source':{}}
    async def tool(name,args):
        return {'items':[{'name':args['keywords'],'provider_id':'B'+args['keywords'],
                         'location':'104.06,30.66','address':'成都市示例路20号','citycode':'028','source':{}}]}
    async def recommend(*args):return '候选'
    monkeypatch.setattr(agent,'tuniu',vendor);monkeypatch.setattr(agent,'local_tool',tool);monkeypatch.setattr(agent,'recommend',recommend)
    asyncio.run(agent.handle(w,'search_hotels',{'keyword':'全季'},lambda _:None))
    assert len(w['candidates'])==4
    assert all(p.get('location') for p in w['candidates'])
    assert all(p.get('address')=='成都市示例路20号' for p in w['candidates'])


def test_route_uses_valid_poi_when_vendor_entrance_is_invalid(monkeypatch):
    seen=[]
    async def tool(name,args):
        seen.append(args);return {'mode':args['mode'],'available':True,'minutes':10}
    monkeypatch.setattr(planning,'local_tool',tool)
    asyncio.run(planning.route_options({'location':'104.06,30.66','entrance':'0,0','citycode':'028'},
                                      {'location':'104.07,30.67','citycode':'028'}))
    assert seen and all(tuple(map(float,x['origin'].split(',')))==(104.06,30.66) for x in seen)


def test_missing_city_does_not_silently_query_qingdao_transit(monkeypatch):
    seen=[]
    async def tool(name,args):
        seen.append(args);return {'mode':args['mode'],'available':True,'minutes':10}
    monkeypatch.setattr(planning,'local_tool',tool)
    asyncio.run(planning.route_options({'location':'104.06,30.66'},{'location':'104.07,30.67'}))
    assert all(x.get('citycode')!='0532' for x in seen)


def test_successful_empty_route_is_distinct_from_query_error(monkeypatch):
    async def amap(*args):return {'data':{'route':{'paths':[]}},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    r=asyncio.run(providers.route('104.06,30.66','104.07,30.67','walking'))
    assert r.get('status')=='no_route'


def test_actual_supplier_branch_alias_matches_only_same_address():
    from app.locations import match_hotel
    hotel={'name':'西安钟楼诺富特酒店','address':'案板街16号（近地铁H口）'}
    rows=[{'name':'西安钟楼诺富特酒店(钟鼓楼回民街店)','address':'案板街16号(地铁H口旁)',
           'location':'108.949899,34.260596','typecode':'100103','provider_id':'correct'},
          {'name':'西安钟楼诺富特酒店(其他店)','address':'其他路25号','location':'108.95,34.26','typecode':'100103','provider_id':'wrong'}]
    matched,count=match_hotel(hotel,rows,'西安')
    assert matched['provider_id']=='correct' and count==1
    rows.append({**rows[0],'provider_id':'uncertain','location':'108.951,34.261'})
    assert match_hotel(hotel,rows,'西安')[0] is None


def test_supplier_province_in_middle_of_name_is_a_geographic_qualifier():
    from app.locations import match_hotel
    p={'name':'维也纳国际酒店·山东青岛火车站东广场栈桥店','address':'湖南路59号'}
    row={'name':'维也纳国际酒店(青岛火车站东广场栈桥店)','address':'湖南路59号(地铁D口旁)',
         'location':'120.314754,36.064978','typecode':'100100','provider_id':'B1'}
    assert match_hotel(p,[row],'青岛')[0]==row


def test_hotel_location_refresh_updates_selected_copy(monkeypatch):
    w={'requirements':{'city':'成都'},'catalog':{'h':{'id':'h','kind':'hotel','name':'全季酒店（成都示例店）','location':None}},
       'hotel':{'id':'h','kind':'hotel','name':'全季酒店（成都示例店）','location':None},'plan':{'stale':False}}
    async def tool(*args):return {'items':[{'name':w['catalog']['h']['name'],'location':'104.06,30.66','address':'示例路20号','provider_id':'B1','source':{}}]}
    monkeypatch.setattr(agent,'local_tool',tool)
    asyncio.run(agent.handle(w,'place_detail',{'id':'h','view':'hotel'},lambda _:None))
    assert w['hotel']['location']=='104.060000,30.660000' and w['hotel']['address']=='示例路20号' and w['plan']['stale']


def test_entrance_without_route_falls_back_to_poi(monkeypatch):
    async def tool(name,args):
        ok=args['origin']=='104.060000,30.660000'
        return {'mode':args['mode'],'available':ok,'status':'available' if ok else 'no_route','minutes':10}
    monkeypatch.setattr(planning,'local_tool',tool)
    options=asyncio.run(planning.route_options({'location':'104.06,30.66','entrance':'104.061,30.661','citycode':'028'},
                                             {'location':'104.07,30.67','citycode':'028'}))
    assert all(x.get('endpoint_fallback') for x in options)


def test_same_point_requires_no_provider_query(monkeypatch):
    async def tool(*args):pytest.fail('Same coordinates should not call route API')
    monkeypatch.setattr(planning,'local_tool',tool)
    options=asyncio.run(planning.route_options({'location':'104.06,30.66'},{'location':'104.060000,30.660000'}))
    assert options[0]['minutes']==0 and options[0]['status']=='same_location'


def test_food_search_filters_confirmed_empty_routes_but_keeps_unknown(monkeypatch):
    from app import foods
    anchor={'id':'a','name':'参照景点','kind':'spot','location':'104.06,30.66','citycode':'028'}
    w={'requirements':{'city':'成都','start_date':'2026-10-20','days':1},'catalog':{'a':anchor},'selected_spots':['a']}
    rows=[{'id':cid,'name':cid,'kind':'food','location':xy,'citycode':'028'} for cid,xy in [('ok','104.07,30.67'),('blocked','104.08,30.68'),('unknown','104.09,30.69')]]
    async def tool(name,args):
        if name=='search_places':return {'items':rows}
        dest=args['destination'];status='available' if dest.startswith('104.07') else 'no_route' if dest.startswith('104.08') else 'query_failed'
        return {'mode':args['mode'],'status':status,'available':status=='available','minutes':10,'reason':'接口超时' if status=='query_failed' else '无方案'}
    async def recommend(*args):return '候选'
    monkeypatch.setattr(foods,'local_tool',tool);monkeypatch.setattr(planning,'local_tool',tool)
    asyncio.run(foods.search(w,{'anchor_id':'a','meal_date':'2026-10-20','meal_period':'lunch'},lambda _:None,recommend))
    assert w['food_query']['ids']==['ok','unknown']
    assert w['catalog']['unknown']['access']['status']=='unknown'
    assert w['food_query']['excluded'][0]['id']=='blocked'


def test_cross_city_transit_uses_each_endpoint_city(monkeypatch):
    seen=[]
    async def tool(name,args):seen.append(args);return {'mode':args['mode'],'available':True,'minutes':20}
    monkeypatch.setattr(planning,'local_tool',tool)
    asyncio.run(planning.route_options({'location':'120.06,30.66','citycode':'0571'},{'location':'120.07,31.67','citycode':'0512'}))
    transit=next(x for x in seen if x['mode']=='transit')
    assert transit['citycode']=='0571' and transit['destination_citycode']=='0512'


def test_no_transit_does_not_hide_a_walkable_restaurant(monkeypatch):
    from app.access import check
    a={'id':'a','name':'景点','location':'104.06,30.66'}
    b={'id':'b','name':'餐厅','kind':'food','location':'104.07,30.67'}
    async def routes(*args):return [{'mode':'walking','available':True,'status':'available','minutes':8},
                                   {'mode':'transit','available':False,'status':'no_route'}]
    result=asyncio.run(check({'requirements':{}},b,a,routes,planning.choose_route))
    assert result['status']=='available'


def test_restaurant_with_insufficient_meal_window_is_screened(monkeypatch):
    from app.access import check
    a={'id':'a','name':'景点','location':'104.06,30.66'}
    b={'id':'b','name':'餐厅','kind':'food','location':'104.07,30.67'}
    w={'requirements':{'start_date':'2026-10-20','days':1},'selected_return':{'departure':'2026-10-20 15:00'}}
    async def routes(*args):return [{'mode':'driving','available':True,'status':'available','minutes':20}]
    result=asyncio.run(check(w,b,a,routes,planning.choose_route,('2026-10-20','lunch')))
    assert result['status']=='time_conflict'


def test_hotel_search_excludes_non_hotel_pois(monkeypatch):
    async def amap(path,params,*args):
        assert params['types']=='100000'
        return {'data':{'pois':[{'id':'h','name':'酒店','typecode':'100100','location':'104.06,30.66'},
                               {'id':'f','name':'酒店餐厅','typecode':'050100','location':'104.06,30.66'}]},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    rows=asyncio.run(providers.search_poi('成都','酒店','hotel'))
    assert [x['provider_id'] for x in rows]==['h']
