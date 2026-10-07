import asyncio
import pytest
from app import discovery,agent,providers,guidance
from app.text import readable

def trip():return {'requirements':{'city':'青岛'},'catalog':{},'selected_spots':[],'messages':[],'tickets':{}}
def poi(i,name=None):return {'id':f's{i}','name':name or f'景点{i}','kind':'spot','rating':4.5}

def test_literal_linebreaks_are_normalized_without_unicode_decoding():
    assert readable('第一行\\n\\n第二行')=='第一行\n\n第二行'
    assert readable('青岛\\r\\n成都')=='青岛\n成都'

def test_first_selection_does_not_claim_an_existing_plan_requires_regeneration():
    w=trip();w['catalog']={'s1':poi(1)}
    answer=asyncio.run(agent.handle(w,'select',{'id':'s1'},lambda x:None))
    assert '完成景点选择' in answer and '重新生成' not in answer

def test_skipping_hotel_clears_selected_hotel_and_marks_plan_stale():
    w=trip();w.update(hotel={'id':'h1'},plan={'stale':False})
    asyncio.run(agent.handle(w,'skip_hotel',{},lambda x:None))
    assert w['hotel'] is None and w['plan']['stale'] and w['stay_skipped']

def test_auxiliary_entries_and_duplicate_parent_names_are_filtered():
    items=[poi(1,'栈桥'),poi(2,'栈桥公园'),poi(3,'栈桥售票处'),poi(4,'栈桥南门'),poi(5,'五四广场')]
    assert [p['name'] for p in discovery.main_pois(items)]==['栈桥','五四广场']

def test_source_backed_destinations_cover_distinct_directions():
    items=discovery.destinations()
    assert {'青岛','成都'}<={p['name'] for p in items}
    assert all(p['highlights'] and p['tags'] and p['source']['url'].startswith('https://') for p in items)

def test_recommendation_order_changes_displayed_page(monkeypatch):
    w=trip();calls=[]
    async def tool(name,args):
        if name=='retrieve_guides':return {'items':[]}
        calls.append(args);return {'items':[poi(i) for i in range(1,9)]}
    async def rank(w,items,*args):
        next(p for p in items if p['id']=='s8')['recommendation_rank']=0
        return '推荐理由\\n第二行'
    monkeypatch.setattr(discovery,'local_tool',tool)
    asyncio.run(discovery.search(w,{'keywords':['景点']},lambda x:None,rank))
    assert discovery.page_info(w)['ids'][0]=='s8'
    assert calls[0]['page']==1 and calls[0]['page_size']==12
    assert discovery.page_info(w)['pages']==1
    assert discovery.page_info(w)['ids']==['s8']  # Only the model's ranked candidate is published.

def test_next_and_previous_page_preserve_selected_items():
    w=trip();w['catalog']={p['id']:p for p in [poi(i) for i in range(1,9)]}
    w['spot_search']={'ids':list(w['catalog']),'page':1,'exhausted':True};w['selected_spots']=['s1']
    first=discovery.page_info(w)['ids']
    asyncio.run(discovery.turn_page(w,{'page':2},lambda x:None,None))
    assert not set(first)&set(discovery.page_info(w)['ids']) and w['selected_spots']==['s1']
    asyncio.run(discovery.turn_page(w,{'page':1},lambda x:None,None))
    assert discovery.page_info(w)['ids']==first

def test_disliked_page_is_replaced_and_selected_spot_is_not_rejected():
    w=trip();w['catalog']={p['id']:p for p in [poi(i) for i in range(1,10)]}
    w['spot_search']={'ids':list(w['catalog']),'page':1,'exhausted':True};w['selected_spots']=['s1']
    asyncio.run(discovery.turn_page(w,{'reject_current':True},lambda x:None,None))
    assert set(w['rejected_spots'])=={'s2','s3','s4'}
    assert not {'s2','s3','s4'}&set(discovery.page_info(w)['ids'])
    assert w['selected_spots']==['s1']

def test_exhausted_page_does_not_recycle_previous_results():
    w=trip();w['catalog']={'s1':poi(1)};w['spot_search']={'ids':['s1'],'page':1,'exhausted':True}
    with pytest.raises(providers.DataError,match='没有更多'):asyncio.run(discovery.turn_page(w,{'page':2},lambda x:None,None))

def test_complete_selection_guides_missing_information_without_opening_random_form():
    w=trip();w['catalog']={'s1':poi(1)};w['selected_spots']=['s1']
    answer=asyncio.run(agent.handle(w,'complete_spots',{},lambda x:None))
    assert w['spots_confirmed'] and '出游日期' in answer and '成人数' in answer
    assert guidance.finish(w)['view']=='hotel'

def test_day_trip_completion_skips_hotel_query():
    w=trip();w['catalog']={'s1':poi(1)};w['selected_spots']=['s1'];w['requirements']['days']=1
    answer=asyncio.run(agent.handle(w,'complete_spots',{},lambda x:None))
    assert '可跳过住宿' in answer and guidance.finish(w)['view']=='transport'

def test_no_spots_cannot_be_confirmed():
    with pytest.raises(providers.DataError,match='至少'):asyncio.run(agent.handle(trip(),'complete_spots',{},lambda x:None))

def test_complete_selection_queries_hotel_when_information_is_ready(monkeypatch):
    w=trip();w['catalog']={'s1':poi(1)};w['selected_spots']=['s1'];w['requirements'].update(start_date='2026-10-08',days=3,adults=2)
    calls=[]
    async def tuniu(service,tool,args):
        calls.append(args);return {'data':{'hotels':[{'hotelId':1,'hotelName':'候选酒店'}]},'source':{}}
    async def local_tool(name,args):return {'items':[]}
    async def recommend(*args):return '已比较住宿候选'
    monkeypatch.setattr(agent,'tuniu',tuniu);monkeypatch.setattr(agent,'local_tool',local_tool);monkeypatch.setattr(agent,'recommend',recommend)
    answer=asyncio.run(agent.handle(w,'complete_spots',{},lambda x:None))
    assert w['spots_confirmed'] and calls[0]['poiName']=='景点1'
    assert '已确认景点' in answer and guidance.finish(w)['view']=='hotel'
    assert any(p['kind']=='hotel' for p in w['catalog'].values())

def test_unshown_destination_cannot_be_selected():
    with pytest.raises(providers.DataError,match='展示'):asyncio.run(agent.handle(trip(),'choose_destination',{'id':'invented'},lambda x:None))

def test_provider_pagination_uses_official_parameter_names(monkeypatch):
    calls=[]
    async def amap(path,args):calls.append(args);return {'data':{'pois':[]},'source':{}}
    monkeypatch.setattr(providers,'amap',amap)
    asyncio.run(providers.search_poi('青岛','风景',page=2,page_size=12))
    assert calls[0]['page_num']==2 and calls[0]['page_size']==12
    with pytest.raises(providers.DataError):asyncio.run(providers.search_poi('青岛','风景',page=0))
