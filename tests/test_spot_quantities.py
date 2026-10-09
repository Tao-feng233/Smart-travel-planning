import asyncio
import pytest
from app import discovery,data_coverage


NAMES=['栈桥景区','八大关风景区','五四广场','崂山风景区','青岛市博物馆','青岛奥帆海洋文化旅游区']


def trip(days=2):
    return {'requirements':{'city':'青岛','days':days},'catalog':{},'selected_spots':[],'messages':[]}


def test_ranking_one_item_cannot_collapse_two_day_candidate_set(monkeypatch):
    w=trip();rows=[{'id':f's{i}','name':name,'kind':'spot','location':f'120.{310+i},36.06'} for i,name in enumerate(NAMES)]
    async def tool(name,args):return {'items':[]} if name=='retrieve_guides' else {'items':rows,'next_offset':len(rows),'exhausted':True}
    async def rank(w,items,*_):items[0]['recommendation_rank']=0;return '优先栈桥'
    monkeypatch.setattr(discovery,'local_tool',tool)
    asyncio.run(discovery.search(w,{},lambda _:None,rank))
    assert len(w['spot_search']['ids'])>=4


def test_existing_official_background_entities_are_recognized():
    assert data_coverage.place_known('青岛','花石楼')
    assert data_coverage.place_known('青岛','中山路')
    assert data_coverage.place_known('青岛','青岛奥帆中心')
    assert not data_coverage.place_known('青岛','凭空产生的景点')


def test_three_days_collects_multiple_four_item_tool_batches(monkeypatch):
    w=trip(3);calls=[]
    rows=[{'id':f's{i}','name':name,'kind':'spot','location':f'120.{310+i},36.06'} for i,name in enumerate(NAMES)]
    async def tool(name,args):
        if name=='retrieve_guides':return {'items':[]}
        calls.append((name,args));offset=args.get('offset',0)
        return {'items':rows[offset:offset+4],'next_offset':offset+4,'exhausted':offset+4>=len(rows)}
    async def rank(*_):return '三天候选'
    monkeypatch.setattr(discovery,'local_tool',tool)
    asyncio.run(discovery.search(w,{},lambda _:None,rank))
    assert len(w['spot_search']['ids'])>=6
    assert [name for name,_ in calls]==['get_spot_candidates','get_spot_candidates']
    assert [args['offset'] for _,args in calls]==[0,4]


def test_more_with_changed_topic_restarts_batch_cursor_and_preserves_choices(monkeypatch):
    w=trip();w['catalog']['old']={'id':'old','name':'崂山风景区','kind':'spot'}
    w.update(selected_spots=['old'],spots_confirmed=True,spot_search={'city':'青岛','ids':['old'],'provider_page':9,'keywords':['崂山']})
    calls=[]
    async def tool(name,args):
        if name=='retrieve_guides':return {'items':[]}
        calls.append(args)
        return {'items':[{'id':'new','name':'栈桥景区','kind':'spot','location':'120.3,36.05'}],'exhausted':True,'next_offset':1}
    async def rank(*_):return '补充'
    monkeypatch.setattr(discovery,'local_tool',tool)
    answer=asyncio.run(discovery.search(w,{'expand_spots':True,'keywords':['休闲','海滨','公园']},lambda _:None,rank))
    assert calls[0]['offset']==0 and calls[0]['exclude_ids']==['old']
    assert w['selected_spots']==['old'] and w['spots_confirmed'] and w['spot_search']['ids']==['new']
    assert '少于本次至少4个' in answer


def test_real_batch_tool_returns_four_then_next_two_from_named_records(monkeypatch):
    from app import spot_candidates
    names=NAMES[:];queries=[]
    monkeypatch.setattr(spot_candidates,'covered_places',lambda city:names)
    async def search(city,keyword,category,page,page_size):
        queries.append((keyword,page_size));i=names.index(keyword)
        return [{'id':str(i),'name':keyword,'kind':'spot','location':'120.3,36.05'}]
    monkeypatch.setattr(spot_candidates.providers,'search_poi',search)
    first=asyncio.run(spot_candidates.get_batch('青岛',['休闲','海滨','公园']))
    second=asyncio.run(spot_candidates.get_batch('青岛',['休闲','海滨','公园'],first['next_offset']))
    assert len(first['items'])==4 and not first['exhausted']
    assert len(second['items'])==2 and second['exhausted']
    assert all(word in names and count==4 for word,count in queries)


def test_batch_tool_skips_missing_coordinates_and_auxiliary_pois(monkeypatch):
    from app import spot_candidates
    monkeypatch.setattr(spot_candidates,'covered_places',lambda city:NAMES)
    async def search(city,keyword,*args,**kwargs):
        i=NAMES.index(keyword)
        return [{'id':str(i),'kind':'spot','name':keyword,'location':None if i==0 else '120.3,36.05'},
                {'id':'gate'+str(i),'kind':'spot','name':keyword+'售票处','location':'120.3,36.05'}]
    monkeypatch.setattr(spot_candidates.providers,'search_poi',search)
    result=asyncio.run(spot_candidates.get_batch('青岛'))
    assert len(result['items'])==4 and result['excluded_locations']==1
    assert all('售票处' not in p['name'] and p.get('location') for p in result['items'])


def test_batch_tool_reports_query_failure_instead_of_data_shortage(monkeypatch):
    from app import spot_candidates
    monkeypatch.setattr(spot_candidates,'covered_places',lambda city:NAMES[:4])
    async def fail(*_,**kwargs):raise discovery.DataError('接口暂不可用')
    monkeypatch.setattr(spot_candidates.providers,'search_poi',fail)
    result=asyncio.run(spot_candidates.get_batch('青岛'))
    assert result['status']=='query_failed' and result['query_failures']==4
    assert result['items']==[] and '地图地点查询' in result['reason']


def test_four_item_batch_tool_is_registered_and_model_can_request_quantity():
    from app.mcp_server import mcp
    from app import agent,goal_agent
    tools=asyncio.run(mcp.list_tools())
    assert any(t.name=='get_spot_candidates' for t in tools)
    assert 'recommend_count' in agent.FUNCTION['function']['parameters']['properties']
    assert 'recommend_count' in goal_agent.READ_TOOLS['search_spots'][1]
