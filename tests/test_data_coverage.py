import asyncio
import copy
import pytest
from app import data_coverage,agent,discovery


def test_directory_is_finite_and_tied_to_saved_corpus():
    rows=discovery.destinations();names=[x['name'] for x in rows]
    # 目的地目录新增洛阳（河南）后 19 → 20；负例城市改用仍未覆盖的苏州。
    assert len(names)==len(set(names))==20
    assert '苏州' not in names and '青岛' in names
    assert data_coverage.canonical_city('山东省青岛市')=='青岛'


def test_unsupported_destination_fails_before_mutating_selections():
    w={'requirements':{'city':'青岛'},'catalog':{'a':{'id':'a'}},'selected_spots':['a'],'hotel':{'id':'h'},'plan':{'stale':False}}
    original=copy.deepcopy(w)
    with pytest.raises(agent.DataError,match='数据库暂时缺失.*苏州.*请选择其他地区'):
        agent.update_requirements(w,{'city':'苏州'})
    assert w==original


def test_explicit_uncovered_place_is_rejected_before_preference_or_query(monkeypatch):
    w={'requirements':{'city':'青岛'},'catalog':{},'selected_spots':[],'messages':[]}
    async def forbidden(*_):pytest.fail('Uncovered place cannot query providers')
    monkeypatch.setattr(discovery,'local_tool',forbidden)
    with pytest.raises(agent.DataError,match='数据库暂时缺失'):
        asyncio.run(agent.execute({'workspace':w,'text':'推荐不存在的奇幻景区','intent':{'action':'search_spots','patch':{},'requested_place':'不存在的奇幻景区'},'progress':lambda _:None}))
    assert not w.get('spot_preference') and not w['catalog']


def test_external_map_results_cannot_expand_local_place_coverage(monkeypatch):
    w={'requirements':{'city':'青岛'},'selected_spots':[],'catalog':{}}
    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        return {'items':[{'id':'real','name':'栈桥景区','kind':'spot','location':'120.31,36.06'},{'id':'outside','name':'外部新景点','kind':'spot','location':'120.32,36.06'}], 'exhausted': True}
    async def recommend(*_):
        return ''
    monkeypatch.setattr(discovery,'local_tool',tool)
    asyncio.run(discovery.search(w, {'keywords': ['风景']}, lambda _: None, recommend))
    assert w['spot_search']['ids'] == ['real']
    assert data_coverage.place_known('青岛','青岛市崂山景区')
