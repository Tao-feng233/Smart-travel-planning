from app.travel.requirements import update_requirements
import asyncio
import pytest
from app.knowledge import coverage as data_coverage
from app.agents import planner as agent
from app.travel import discovery


def test_directory_is_finite_and_tied_to_saved_corpus():
    rows=discovery.destinations();names=[x['name'] for x in rows]
    # 目的地目录新增洛阳（河南）后 19 → 20；负例城市改用仍未覆盖的苏州。
    assert len(names)==len(set(names))==20
    assert '苏州' not in names and '青岛' in names
    assert data_coverage.canonical_city('山东省青岛市')=='青岛'


def test_destination_outside_local_corpus_can_update_requirements():
    w={'requirements':{'city':'青岛'},'catalog':{'a':{'id':'a'}},'selected_spots':['a'],'hotel':{'id':'h'},'plan':{'stale':False}}
    update_requirements(w,{'city':'苏州'})
    assert w['requirements']['city']=='苏州' and w['selected_spots']==[]
    assert w['plan']['stale']


def test_explicit_uncovered_place_reaches_search_instead_of_local_rejection(monkeypatch):
    w={'requirements':{'city':'青岛'},'catalog':{},'selected_spots':[],'messages':[]}
    seen=[]
    async def search(w,action,args,progress):seen.append(args);return '本次未核实到该地点'
    monkeypatch.setattr(agent,'handle',search)
    asyncio.run(agent.execute({'workspace':w,'text':'推荐一个资料名单外的地点','intent':{
        'action':'search_spots','patch':{},'requested_place':'名单外的地点',
        'mission':{'mode':'query','objective':'查询地点','scopes':['spots'],'multi_step':False}},'progress':lambda _:None}))
    assert seen[0]['requested_place']=='名单外的地点' and not w['catalog']


def test_web_candidates_can_expand_beyond_local_place_coverage(monkeypatch,web_candidates):
    w={'requirements':{'city':'青岛'},'selected_spots':[],'catalog':{}}
    rows=[{'id':'real','name':'栈桥景区','kind':'spot','location':'120.31,36.06'},{'id':'outside','name':'外部新景点','kind':'spot','location':'120.32,36.06'}]
    web_candidates(rows)
    async def tool(name, args):return {'items':rows}
    async def recommend(*_):
        return ''
    monkeypatch.setattr(discovery,'local_tool',tool)
    asyncio.run(discovery.search(w, {'keywords': ['风景']}, lambda _: None, recommend))
    assert w['spot_search']['ids'] == ['real','outside']
    assert data_coverage.place_known('青岛','青岛市崂山景区')
