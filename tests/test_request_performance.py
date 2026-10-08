import asyncio
import json

from app import providers,agent,request_cache,storage


def test_identical_inflight_map_queries_share_one_vendor_request(monkeypatch):
    calls=[];cache={}
    class Response:
        status_code=200
        def json(self):return {'status':'1','pois':[]}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):calls.append(True);await asyncio.sleep(.02);return Response()
    async def slot():pass
    monkeypatch.setattr(providers.httpx,'AsyncClient',Client);monkeypatch.setattr(providers,'cached',lambda key:cache.get(key))
    monkeypatch.setattr(providers,'put_cache',lambda key,value,ttl:cache.update({key:value}));monkeypatch.setattr(providers,'amap_slot',slot)
    async def run():
        try:return await asyncio.gather(*(providers.amap('/v5/place/text',{'keywords':'栈桥'}) for _ in range(3)))
        finally:await request_cache.close()
    results=asyncio.run(run())
    assert len(calls)==1
    results[0]['source']['kind']='changed'
    assert results[1]['source']['kind']!='changed'


def test_repeated_llm_requests_reuse_http_connection_pool(monkeypatch):
    clients=[]
    class Response:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'ok'}}]}
    class Client:
        def __init__(self,**kwargs):clients.append(self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return Response()
    monkeypatch.setattr(providers.httpx,'AsyncClient',Client);monkeypatch.setattr(providers,'record_llm_call',lambda *a,**k:None)
    monkeypatch.setattr(providers,'setting',lambda key,default='':'https://example.invalid' if key=='LLM_BASE_URL' else 'fixture')
    async def run():
        try:await providers.llm([]);await providers.llm([])
        finally:await request_cache.close()
    asyncio.run(run())
    assert len(clients)==1


def test_recommendation_cache_reuses_identical_facts_and_invalidates_changes(monkeypatch):
    cache={};calls=[]
    monkeypatch.setattr(storage,'cached',lambda key:cache.get(key))
    monkeypatch.setattr(storage,'put_cache',lambda key,value,ttl:cache.update({key:value}))
    async def model(*args,**kwargs):
        calls.append(True);await asyncio.sleep(.01)
        return {'content':json.dumps({'recommendations':[{'id':'s','reason':'已知特色','evidence_ids':[]}],'summary':'查询比较完成'})},{}
    monkeypatch.setattr(agent,'llm',model)
    w={'id':'cache-trip','requirements':{'city':'青岛','start_date':'2026-10-12','days':3}}
    items=[{'id':'s','name':'栈桥','kind':'spot'}]
    async def run():
        await asyncio.gather(agent.recommend(w,items,'比较景点'),agent.recommend(w,items,'比较景点'))
        assert len(calls)==1
        await agent.recommend(w,items,'比较景点');assert len(calls)==1
        w['requirements']['days']=4
        await agent.recommend(w,items,'比较景点');assert len(calls)==2
        items[0]['opening_hours']='08:00–18:00'
        await agent.recommend(w,items,'比较景点');assert len(calls)==3
        await request_cache.close()
    asyncio.run(run())


def test_cancelling_one_waiter_does_not_cancel_shared_supplier_query():
    async def run():
        ready=asyncio.Event();finish=asyncio.Event();calls=[]
        async def supplier():calls.append(True);ready.set();await finish.wait();return {'items':['real']}
        first=asyncio.create_task(request_cache.singleflight(('cancel-test',),supplier))
        await ready.wait()
        second=asyncio.create_task(request_cache.singleflight(('cancel-test',),supplier))
        await asyncio.sleep(0);first.cancel()
        try:await first
        except asyncio.CancelledError:pass
        finish.set();result=await second
        assert result=={'items':['real']} and len(calls)==1
        await request_cache.close()
    asyncio.run(run())
