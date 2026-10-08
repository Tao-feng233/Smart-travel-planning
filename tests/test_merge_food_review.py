import asyncio
import copy

import pytest

from app import foods, planning, providers
from app.providers import DataError


def trip():
    return {'requirements':{'city':'洛阳','start_date':'2026-10-20','days':2},
            'catalog':{'s':{'id':'s','kind':'spot','name':'景点','location':'112.41,34.56'}},
            'selected_spots':['s'],'food_query':{'ids':['previous']},'messages':[]}


async def recommend(*args):return '已比较候选'


def test_supplier_failure_stops_fallback_and_preserves_previous_candidates(monkeypatch):
    w=trip();previous=copy.deepcopy(w['food_query']);calls=[]
    async def tool(*args):calls.append(True);raise DataError('接口请求失败，请稍后重试')
    monkeypatch.setattr(foods,'local_tool',tool)
    with pytest.raises(DataError,match='接口请求失败'):
        asyncio.run(foods.search(w,{},lambda _:None,recommend))
    assert len(calls)==1 and w['food_query']==previous


def test_coverage_label_matches_radius_sent_to_actual_provider_adapter(monkeypatch):
    w=trip();sent=[]
    async def amap(path,args,*unused):
        sent.append(dict(args))
        rows=[{'id':'f','name':'餐厅','location':'112.42,34.57'}] if args.get('radius')==10000 else []
        return {'data':{'pois':rows},'source':{'name':'合成来源'}}
    async def tool(name,args):
        return {'items':await providers.search_poi(args['city'],args['keywords'],args['category'],
                     location=args.get('location'),radius=args.get('radius',5000))}
    async def routes(*args):return [{'mode':'walking','available':True,'status':'available','minutes':5}]
    monkeypatch.setattr(providers,'amap',amap);monkeypatch.setattr(foods,'local_tool',tool);monkeypatch.setattr(planning,'route_options',routes)
    asyncio.run(foods.search(w,{},lambda _:None,recommend))
    assert w['food_query']['ids'] and sent[-1]['radius']==10000
    assert w['food_query']['scope']=='周边10公里'
