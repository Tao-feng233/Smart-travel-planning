import asyncio,copy,json
import pytest
from app.agent import handle,execute
from app.providers import DataError

def work():
 return {'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':3,'adults':2,'rooms':1},'catalog':{},'selected_spots':[],'hotel':None,'selected_transport':None,'selected_return':None,'messages':[],'tickets':{}}
def run(w,a,args):return asyncio.run(handle(w,a,args,lambda _:None))
def hotel(w):
 h={'id':'h1','kind':'hotel','name':'示例酒店','detail':{'roomTypes':[{'roomTypeId':1,'roomTypeName':'悦享大床房','maxOccupancy':2,'ratePlans':[{'vendorRatePlanId':'rate1','ratePlanName':'标准价','rmbPrices':'289','mealText':'无早餐','cancelText':'入住前取消'}]}]}}
 w['catalog']['h1']=h;w['hotel']=copy.deepcopy(h);return h

def test_room_click_saves_actual_rate_and_replaces_without_extra_rooms():
 from app.choices import room_choices
 w=work();h=hotel(w);rooms=room_choices(h,w['requirements']);run(w,'select_room',{'id':rooms[0]['id']})
 assert w['selected_room']['name']=='悦享大床房' and w['selected_room']['price']=='289'
 run(w,'select_room',{'id':rooms[0]['id']});assert w['selected_room']['quantity']==1

def test_room_insufficient_capacity_blocks_mutation():
 from app.choices import room_choices
 w=work();h=hotel(w);w['requirements']['adults']=3;rooms=room_choices(h,w['requirements'])
 with pytest.raises(DataError,match='容纳'):run(w,'select_room',{'id':rooms[0]['id']})
 assert not w.get('selected_room')

def test_multiple_same_direction_requires_explicit_replacement_and_mixed_return_allowed():
 w=work();w['catalog']={i:{'id':i,'kind':k,'name':i,'direction':d} for i,k,d in [('t1','train','outbound'),('t2','train','outbound'),('f1','flight','return')]}
 run(w,'select',{'id':'t1'})
 with pytest.raises(DataError,match='替换'):run(w,'select',{'id':'t2'})
 assert w['selected_transport']['id']=='t1'
 run(w,'select',{'id':'t2','replace':True});run(w,'select',{'id':'f1'})
 assert w['selected_transport']['kind']=='train' and w['selected_return']['kind']=='flight'

def test_requested_hotel_brand_passed_and_empty_results_not_old_recommendations(monkeypatch):
 import app.agent as a
 w=work();w['selected_spots']=['s1'];w['catalog']['s1']={'id':'s1','kind':'spot','name':'栈桥'};seen=[]
 async def provider(s,t,p):seen.append(p);return {'data':{'hotels':[]},'source':{'name':'测试源'}}
 monkeypatch.setattr(a,'tuniu',provider)
 answer=run(w,'search_hotels',{'keyword':'汉庭'})
 assert seen[0]['keyword']=='汉庭' and '未查到' in answer and '汉庭' in answer and '偏好' in answer
 assert w['hotel_query']['ids']==[]

def test_train_time_parameters_and_conventional_seat(monkeypatch):
 import app.agent as a
 w=work();seen=[]
 async def provider(s,t,p):seen.append(p);return {'data':{'data':[{'trainNum':'Z318','departureTime':'2026-10-12 13:06','arrivalTime':'2026-10-12 23:27','price':{'yzPrice':'138.5'},'seatAvailable':{'yzNum':99}}]},'source':{'name':'测试源'}}
 monkeypatch.setattr(a,'tuniu',provider);run(w,'train',{'time_start':'12:00','time_end':'18:00','train_type':'regular'})
 assert seen[0]['departureTime']=='12:00-18:00'
 p=w['transport']['items'][0];assert p['seat_type']=='硬座' and p['price']=='138.5'

def test_origin_change_keeps_lodging_but_invalidates_transport_queries():
 from app.agent import update_requirements
 w=work();hotel(w);w['selected_room']={'id':'r1'};w['transport_queries']={'train:outbound':{'items':[{'id':'old'}]}}
 update_requirements(w,{'origin':'上海'})
 assert not w['hotel'].get('stale') and w['selected_room']['id']=='r1'
 assert not w.get('transport_queries') and w['selected_transport'] is None

def test_no_result_query_clears_only_current_transport_batch(monkeypatch):
 import app.agent as a
 w=work();w['selected_transport']={'id':'chosen'};w['transport_queries']={'flight:return':{'items':[{'id':'old'}]}}
 async def provider(s,t,p):return {'data':{'data':[]},'source':{'name':'测试'}}
 monkeypatch.setattr(a,'tuniu',provider);answer=run(w,'flight',{'direction':'return'})
 assert not w['transport_queries']['flight:return']['items'] and w['selected_transport']['id']=='chosen'
 assert '未查到' in answer

def test_completion_prefills_both_directions_and_keeps_existing_confirmation(monkeypatch):
 import app.agent as a
 from app.choices import room_choices
 w=work();h=hotel(w);w['selected_room']=room_choices(h,w['requirements'])[0]
 seen=[]
 async def provider(s,t,p):
  seen.append(p);day=p['departureDate']
  return {'data':{'data':[{'trainNum':'G123','departureTime':day+' 10:00','arrivalTime':day+' 13:00','price':{'edzPrice':'299'},'seatAvailable':{'edzNum':99}}]},'source':{'name':'测试'}}
 monkeypatch.setattr(a,'tuniu',provider);answer=run(w,'complete_hotel',{})
 assert w['selected_transport']['selection_status']=='recommended' and w['selected_return']['selection_status']=='recommended'
 assert seen[0]['departureCityName']=='郑州' and seen[1]['departureCityName']=='青岛'
 assert '推荐' in answer
 run(w,'select',{'id':w['selected_transport']['id']});assert w['selected_transport']['selection_status']=='confirmed'
 before=w['selected_transport'].copy();run(w,'complete_hotel',{});assert w['selected_transport']==before and len(seen)==2
