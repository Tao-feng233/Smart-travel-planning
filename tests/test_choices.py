import asyncio,copy,json
import pytest
from app.agents.planner import handle, execute
from app.core.errors import DataError

def work():
 return {'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':3,'adults':2,'rooms':1},'catalog':{},'selected_spots':[],'hotel':None,'selected_transport':None,'selected_return':None,'messages':[],'tickets':{}}
def run(w,a,args):return asyncio.run(handle(w,a,args,lambda _:None))
def hotel(w):
 h={'id':'h1','kind':'hotel','name':'示例酒店','detail':{'roomTypes':[{'roomTypeId':1,'roomTypeName':'悦享大床房','maxOccupancy':2,'ratePlans':[{'vendorRatePlanId':'rate1','ratePlanName':'标准价','rmbPrices':'289','mealText':'无早餐','cancelText':'入住前取消'}]}]}}
 w['catalog']['h1']=h;w['hotel']=copy.deepcopy(h);return h

# 住宿按晚指定：fixture 里把三晚都指定给同一家，代表用户逐晚选好。
def assign_nights(w,hid='h1'):
 w['stay_hotels']={d:hid for d in ('2026-10-12','2026-10-13','2026-10-14')};return w

def test_room_click_saves_actual_rate_and_replaces_without_extra_rooms():
 from app.travel.choices import room_choices
 w=work();h=hotel(w);rooms=room_choices(h,w['requirements']);run(w,'select_room',{'id':rooms[0]['id']})
 assert w['selected_room']['name']=='悦享大床房' and w['selected_room']['price']=='289'
 run(w,'select_room',{'id':rooms[0]['id']});assert w['selected_room']['quantity']==1

def test_room_insufficient_capacity_blocks_mutation():
 from app.travel.choices import room_choices
 w=work();h=hotel(w);w['requirements']['adults']=3;rooms=room_choices(h,w['requirements'])
 with pytest.raises(DataError,match='容纳'):run(w,'select_room',{'id':rooms[0]['id']})
 assert not w.get('selected_room')

def test_requested_hotel_brand_passed_and_empty_results_not_old_recommendations(monkeypatch):
 import app.agents.planner as a
 w=work();w['selected_spots']=['s1'];w['catalog']['s1']={'id':'s1','kind':'spot','name':'栈桥'};seen=[]
 async def provider(s,t,p):seen.append(p);return {'data':{'hotels':[]},'source':{'name':'测试源'}}
 monkeypatch.setattr(a,'tuniu',provider)
 answer=run(w,'search_hotels',{'keyword':'汉庭'})
 assert seen[0]['keyword']=='汉庭' and '未查到' in answer and '汉庭' in answer and '偏好' in answer
 assert w['hotel_query']['ids']==[]

def test_train_time_parameters_and_conventional_seat(monkeypatch):
 import app.agents.planner as a
 w=work();seen=[]
 async def provider(s,t,p):seen.append(p);return {'data':{'data':[{'trainNum':'Z318','departureTime':'2026-10-12 13:06','arrivalTime':'2026-10-12 23:27','price':{'yzPrice':'138.5'},'seatAvailable':{'yzNum':99}}]},'source':{'name':'测试源'}}
 monkeypatch.setattr(a,'tuniu',provider);run(w,'train',{'time_start':'12:00','time_end':'18:00','train_type':'regular'})
 assert seen[0]['departureTime']=='12:00-18:00'
 p=w['transport']['items'][0];assert p['seat_type']=='硬座' and p['price']=='138.5'

def test_origin_change_keeps_lodging_but_invalidates_transport_queries():
 from app.travel.requirements import update_requirements
 w=work();hotel(w);w['selected_room']={'id':'r1'};w['transport_queries']={'train:outbound':{'items':[{'id':'old'}]}}
 update_requirements(w,{'origin':'上海'})
 assert not w['hotel'].get('stale') and w['selected_room']['id']=='r1'
 assert not w.get('transport_queries') and w['selected_transport'] is None

def test_no_result_query_clears_only_current_transport_batch(monkeypatch):
 import app.agents.planner as a
 w=work();w['selected_transport']={'id':'chosen'};w['transport_queries']={'flight:return':{'items':[{'id':'old'}]}}
 async def provider(s,t,p):return {'data':{'data':[]},'source':{'name':'测试'}}
 monkeypatch.setattr(a,'tuniu',provider);answer=run(w,'flight',{'direction':'return'})
 assert not w['transport_queries']['flight:return']['items'] and w['selected_transport']['id']=='chosen'
 assert '未查到' in answer
