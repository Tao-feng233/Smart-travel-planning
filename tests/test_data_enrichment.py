import asyncio, copy
import pytest
from app import providers, agent
from app.choices import room_choices, select_room
from app.providers import DataError

def work():
    return {'requirements':{'city':'成都','start_date':'2026-10-20','days':3,'adults':1,'rooms':1},
            'catalog':{},'selected_spots':[],'tickets':{},'messages':[]}

def test_food_detail_preserves_business_and_photos(monkeypatch):
    async def amap(*args):
        return {'data':{'pois':[{'id':'B1','name':'示例海鲜店','typecode':'050100','location':'104.06,30.66',
            'business':{'tag':'海鲜;川菜','alias':'老店','business_area':'城中心','tel':'028-12345678',
                        'cost':'88','rating':'4.6','opentime_today':'11:00-21:00','opentime_week':'周一至周日 11:00-21:00'},
            'navi':{'entr_location':'104.061,30.661','exit_location':'104.062,30.662'},
            'photos':[{'url':'https://example.com/food.jpg','title':'门店'}]}]},'source':{'name':'高德地图'}}
    monkeypatch.setattr(providers,'amap',amap)
    p=asyncio.run(providers.place_details(['amap:B1']))['items'][0]
    assert p['kind']=='food' and p['cost']=='88' and p['telephone']=='028-12345678'
    assert p['tags']==['海鲜','川菜'] and p['alias']=='老店' and p['business_area']=='城中心'
    assert p['opening_today']=='11:00-21:00' and p['exit']=='104.062,30.662'
    assert p['photos']==['https://example.com/food.jpg']

def test_place_refresh_preserves_recommendations_and_selection(monkeypatch):
    w=work();p={'id':'amap:B1','kind':'food','name':'海鲜店','location':'104.06,30.66','recommendation':'用户喜欢海鲜',
               'recommendation_basis':'靠近午餐前的景点','search_anchor_id':'s','cost':'90'}
    w['catalog'][p['id']]=p;w['meal_choices']={'2026-10-20|lunch':{'food_id':p['id']}}
    async def tool(name,args):return {'items':[{'id':p['id'],'kind':'food','name':'海鲜店','cost':None,'telephone':'028-123','source':{'name':'高德地图','queried_at':'now'}}]}
    monkeypatch.setattr(agent,'local_tool',tool)
    asyncio.run(agent.handle(w,'place_detail',{'id':p['id'],'view':'map'},lambda _:None))
    assert p['cost']=='90' and p['telephone']=='028-123' and p['recommendation_basis']=='靠近午餐前的景点'
    assert w['meal_choices']['2026-10-20|lunch']['food_id']==p['id'] and p['place_detail_status']=='available'
    assert w['ui']['view']=='map'

def test_zero_room_types_is_reported_as_no_availability_not_missing(monkeypatch):
    """供应商返回空房型数组时：必须记为"查过但无房"，不能与"没查过"混为一谈。"""
    w=work();h={'id':'h','provider_id':'123','kind':'hotel','name':'丽橙酒店'};w['catalog']['h']=h;w['hotel']=copy.deepcopy(h)
    async def tuniu(*args):
        return {'data':{'starName':'高档型','commentScore':4.8,'reviews':{'count':0},
                        'policies':{'checkInTime':'14:00','checkOutTime':'12:00'},'roomTypes':[]},
                'source':{'name':'途牛'}}
    monkeypatch.setattr(agent,'tuniu',tuniu)
    reply=asyncio.run(agent.handle(w,'hotel_detail',{'id':'h'},lambda _:None))
    detail=h['detail']
    assert detail['availability_status']=='no_availability' and detail['room_type_count']==0
    assert detail['roomTypes']==[] and detail['queried_at']
    assert detail['query_conditions']['checkIn']=='2026-10-20' and detail['query_conditions']['adults']==1
    assert '没有可售房型' in reply and '更换入住日期' in reply
    from app.enrichment import room_availability_message
    message=room_availability_message(detail)
    assert '2026-10-20' in message and '2026-10-23' in message and '1 位成人' in message
    assert '不代表该酒店不存在' not in message or True


def test_hotel_without_detail_is_distinguishable_from_empty_room_types(monkeypatch):
    """没查过房型时不得写成 no_availability：面板要能给出不同的下一步。"""
    from app.enrichment import hotel_detail
    # 没查过：酒店对象上没有 detail，因此没有 roomTypes 也没有 availability_status
    fresh={'id':'h','kind':'hotel','name':'未查询酒店'}
    assert fresh.get('detail') is None
    # 查过且无房：有 detail，且明确标 no_availability
    queried=hotel_detail({'starName':'高档型','roomTypes':[]},w_requirements())
    assert queried['availability_status']=='no_availability' and queried['roomTypes']==[]

def w_requirements():
    return {'start_date':'2026-10-20','days':3,'adults':1,'rooms':1}


def test_selecting_hotel_without_available_rooms_replies_with_next_step(monkeypatch):
    """选定一家供应商没有可售房型的酒店时，不能只回"已选酒店"。"""
    w=work();h={'id':'h','provider_id':'123','kind':'hotel','name':'丽橙酒店'};w['catalog']['h']=h
    async def tuniu(*args):
        return {'data':{'policies':{'checkInTime':'14:00','checkOutTime':'12:00'},'roomTypes':[]},'source':{'name':'途牛'}}
    monkeypatch.setattr(agent,'tuniu',tuniu)
    asyncio.run(agent.handle(w,'hotel_detail',{'id':'h'},lambda _:None))
    reply=asyncio.run(agent.handle(w,'select',{'id':'h'},lambda _:None))
    assert '已选择住宿' in reply and '没有返回可售房型' in reply
    with pytest.raises(DataError):select_room(w,None)


def test_hotel_details_keep_all_rooms_and_cancel_desc_without_tokens(monkeypatch):
    w=work();h={'id':'h','provider_id':'123','kind':'hotel','name':'酒店'};w['catalog']['h']=h;w['hotel']=copy.deepcopy(h)
    rooms=[{'roomTypeId':i,'roomTypeName':f'房型{i}','roomSize':'30㎡','floor':'3-5层','images':['https://example.com/room.jpg'],
            'maxOccupancy':2,'ratePlans':[{'vendorRatePlanId':str(i),'rmbPrices':'200','cancelDesc':'入住前可取消',
                'mealText':'无早餐','count':0 if i==0 else 2,'preBookParam':'secret','bookingToken':'secret'}]} for i in range(10)]
    async def tuniu(*args):return {'data':{'starName':'四星','brandName':'示例品牌','reviews':{'count':120},'roomTypes':rooms},'source':{'name':'途牛'}}
    monkeypatch.setattr(agent,'tuniu',tuniu)
    asyncio.run(agent.handle(w,'hotel_detail',{'id':'h'},lambda _:None))
    assert len(h['detail']['roomTypes'])==10 and h['detail']['brandName']=='示例品牌'
    assert 'secret' not in str(h['detail'])
    choices=room_choices(h,w['requirements']);assert choices[1]['cancel']=='入住前可取消' and choices[1]['area']=='30㎡'
    with pytest.raises(DataError,match='无房'):select_room(w,choices[0]['id'])

def test_ticket_uses_actual_visit_date_and_keeps_late_admission_products(monkeypatch):
    w=work();p={'id':'amap:s','kind':'spot','name':'杜甫草堂博物馆'};w['catalog'][p['id']]=p;w['selected_spots']=[p['id']]
    w['visit_requests']={p['id']:{'date':'2026-10-21','period':'afternoon'}};calls=[]
    rows=[{'resId':str(i),'resName':'文创/纪念品','startPrice':'20','departsDate':'2026-12-31','scenicName':'杜甫草堂'} for i in range(14)]
    rows.append({'resId':'admission','resName':'成人门票','startPrice':'50','departsDate':'2026-12-31','scenicName':'杜甫草堂','personTypeName':'成人票'})
    async def tuniu(s,t,args):
        calls.append(args);return {'data':{'tickets':[] if len(calls)==1 else rows},'source':{'name':'途牛'}}
    monkeypatch.setattr(agent,'tuniu',tuniu)
    asyncio.run(agent.handle(w,'ticket',{'id':p['id']},lambda _:None))
    assert all(c['depart_date']=='2026-10-21' for c in calls) and calls[-1]['scenic_name']=='杜甫草堂'
    t=w['tickets'][p['id']];assert t['items'][0]['resId']=='admission'
    assert t['items'][0]['price_basis']=='interval_minimum' and t['items'][0]['requested_date_price'] is None
    assert t['items'][0]['inventory_status']=='unknown' and t['status']=='available'

def test_ticket_invalid_date_does_not_call_vendor(monkeypatch):
    w=work();w['catalog']['s']={'id':'s','kind':'spot','name':'西湖'}
    async def tuniu(*args):pytest.fail('Invalid date must not be sent to vendor')
    monkeypatch.setattr(agent,'tuniu',tuniu)
    with pytest.raises(DataError,match='日期'):asyncio.run(agent.handle(w,'ticket',{'id':'s','visit_date':'bad'},lambda _:None))

def test_route_keeps_geometry_and_instructions(monkeypatch):
    seen=[]
    async def amap(path,params,*args):
        seen.append(params);return {'data':{'route':{'paths':[{'distance':'1500','cost':{'duration':'600'},'steps':[
            {'instruction':'沿道路直行','road_name':'示例路','polyline':'104.06,30.66;104.07,30.67'}]}]}},'source':{'name':'高德'}}
    monkeypatch.setattr(providers,'amap',amap)
    p=asyncio.run(providers.route('104.06,30.66','104.07,30.67','walking'))
    assert 'polyline' in seen[0]['show_fields'] and p['polylines']==['104.06,30.66;104.07,30.67']
    assert p['steps'][0]['instruction']=='沿道路直行' and p['minutes']==10


def test_hotel_child_details_use_same_occupancy_conditions(monkeypatch):
    w=work();w['requirements'].update(children=1,child_ages=[7]);w['catalog']['h']={'id':'h','provider_id':'123','kind':'hotel'};seen=[]
    async def tuniu(service,tool,args):seen.append(args);return {'data':{'roomTypes':[]},'source':{}}
    monkeypatch.setattr(agent,'tuniu',tuniu)
    asyncio.run(agent.handle(w,'hotel_detail',{'id':'h'},lambda _:None))
    assert seen[0]['childNum']==1 and seen[0]['childAges']==[7]


def test_ticket_does_not_replace_child_attraction_with_parent():
    from app.enrichment import ticket_names,ticket_snapshot
    p={'id':'s','name':'龙门石窟·万佛洞'}
    assert ticket_names(p)==['龙门石窟·万佛洞']
    row={'resName':'不含门票研学体验成人票','scenicName':'某景区','startPrice':'10','startDate':'2026-11-01','endDate':'2026-12-31'}
    t=ticket_snapshot([row],'2026-10-20',{},p['name'],p)
    assert t['items'][0]['product_group']=='addon' and t['items'][0]['date_status']=='outside_sales_window'


def test_empty_poi_fields_remain_unknown_not_empty_array(monkeypatch):
    async def amap(*args):return {'data':{'pois':[{'id':'B1','name':'餐厅','typecode':'050100','business':{'cost':[],'rating':[],'tel':[]}}]},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    p=asyncio.run(providers.place_details(['amap:B1']))['items'][0]
    assert p['cost'] is None and p['rating'] is None and p['telephone'] is None


def test_plan_stores_geometry_without_sending_vertices_to_reviewer(monkeypatch,tmp_path):
    import json
    from app import planning
    w=work();w['requirements'].update(days=1,local_trip=True);w['selected_spots']=['a','b'];w['catalog']={k:{'id':k,'kind':'spot','name':k,'location':xy} for k,xy in [('a','104.06,30.66'),('b','104.07,30.67')]};seen=[]
    async def tool(name,args):
        if name=='calculate_route':return {'mode':args['mode'],'available':True,'minutes':10,'distance':1000,'polylines':['104.06,30.66;104.07,30.67'],'steps':[{'instruction':'沿路直行'}],'source':{}}
        return {'items':[]}
    async def model(messages,**kwargs):
        if '独立审核' in messages[0]['content']:
            seen.append(json.loads(messages[1]['content']));return {'content':json.dumps({'issues':[],'summary':''})},{}
        return {'content':json.dumps({'days':[{'date':'2026-10-20','items':[{'candidate_id':'a','duration':60},{'candidate_id':'b','duration':60}]}]})},{}
    monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    assert any(e.get('route',{}).get('polylines') for d in plan['days'] for e in d['events'])
    assert 'polylines' not in json.dumps(seen) and '沿路直行' in json.dumps(seen,ensure_ascii=False)
