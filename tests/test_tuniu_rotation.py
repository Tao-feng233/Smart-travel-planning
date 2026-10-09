import asyncio
import json
import sqlite3
import pytest
from app import config,storage,providers,agent
from app.integrations import tuniu,tuniu_pool


@pytest.fixture
def setup(monkeypatch,tmp_path):
    values={f'TUNIU_API_KEY_{i}':f'synthetic-secret-{i}' for i in range(1,5)}
    monkeypatch.setattr(config,'VALUES',values)
    monkeypatch.setattr(storage,'DB',tmp_path/'isolated.db')
    storage.init()
    class Clock:
        stamp=1000.0
        sleeps=[]
        def time(self):return self.stamp
        async def sleep(self,seconds):self.sleeps.append(seconds);self.stamp+=seconds
    clock=Clock()
    monkeypatch.setattr(tuniu_pool.time,'time',clock.time)
    return values,clock


def release(pool,credential):pool.busy.discard(credential.account)


def test_four_accounts_rotate_then_wait_only_for_reused_account(setup):
    _,clock=setup
    async def run():
        pool=tuniu_pool.AccountPool(config.tuniu_credentials());seen=[]
        for _ in range(4):
            async with pool.acquire() as c:seen.append(c.slot)
        assert seen==[f'TUNIU_API_KEY_{i}' for i in range(1,5)]
        assert clock.sleeps==[]
        monkeypatch_sleep=asyncio.sleep
        tuniu_pool.asyncio.sleep=clock.sleep
        try:
            async with pool.acquire() as c:assert c.slot=='TUNIU_API_KEY_1'
        finally:tuniu_pool.asyncio.sleep=monkeypatch_sleep
        assert sum(clock.sleeps)==13
    asyncio.run(run())


def test_skip_cooling_exhausted_and_disabled_accounts(setup):
    values,clock=setup;values['TUNIU_DAILY_LIMIT']='2'
    pool=tuniu_pool.AccountPool(config.tuniu_credentials());a,b,c,d=pool.credentials
    with storage.connect() as db:
        db.executemany('INSERT INTO calls VALUES(?,?)',[(a.account,clock.time()),(b.account,900),(b.account,950)])
    pool.cooldown(c,60)
    picked,_=pool.reserve(clock.time());assert picked==d;release(pool,picked)
    assert tuniu_pool.remaining_budget()==4


def test_shared_account_labels_and_duplicate_keys_do_not_multiply_quota(setup):
    values,clock=setup;values.update(TUNIU_API_ACCOUNT_1='same',TUNIU_API_ACCOUNT_2='same',TUNIU_API_KEY_4=values['TUNIU_API_KEY_3'])
    credentials=config.tuniu_credentials();assert len(credentials)==3
    assert credentials[0].account==credentials[1].account
    pool=tuniu_pool.AccountPool(credentials)
    first,_=pool.reserve(clock.time());release(pool,first)
    second,_=pool.reserve(clock.time());assert second.slot=='TUNIU_API_KEY_3'
    assert tuniu_pool.remaining_budget()==78


def test_numbered_keys_precede_legacy_and_legacy_usage_is_retained(setup):
    values,clock=setup;values['TUNIU_API_KEY']=values['TUNIU_API_KEY_2']
    assert len(config.tuniu_credentials())==4
    with storage.connect() as db:db.execute('INSERT INTO calls VALUES(?,?)',('tuniu',clock.time()))
    credentials=config.tuniu_credentials();pool=tuniu_pool.AccountPool(credentials)
    a,_=pool.reserve(clock.time());release(pool,a)
    c,_=pool.reserve(clock.time());assert c.slot=='TUNIU_API_KEY_3'
    values.clear();values['TUNIU_API_KEY']='legacy-synthetic-secret'
    assert config.tuniu_credentials()[0].account=='tuniu' and config.configured()['TUNIU_API_KEY']


def test_reservations_survive_pool_restart_and_do_not_contain_keys(setup):
    _,clock=setup;creds=config.tuniu_credentials();pool=tuniu_pool.AccountPool(creds)
    a,_=pool.reserve(clock.time());release(pool,a)
    pool=tuniu_pool.AccountPool(creds);b,_=pool.reserve(clock.time());assert b.slot=='TUNIU_API_KEY_2'
    with storage.connect() as db:rows=db.execute('SELECT provider FROM calls').fetchall()
    assert not any(c.key in str(rows) or c.key in repr(c) for c in creds)


def test_all_accounts_exhausted_fails_without_waiting(setup):
    values,clock=setup;values['TUNIU_DAILY_LIMIT']='1'
    pool=tuniu_pool.AccountPool(config.tuniu_credentials())
    for _ in range(4):c,_=pool.reserve(clock.time());release(pool,c)
    with pytest.raises(providers.DataError,match='预算已用完'):pool.reserve(clock.time())
    assert tuniu_pool.remaining_budget()==0


def test_real_adapter_uses_rotation_cache_and_coalesces_requests(setup,monkeypatch):
    _,clock=setup;seen=[]
    async def query(service,tool,args,credential):seen.append(credential.slot);return {'quote':args['query']}
    monkeypatch.setattr(tuniu,'query',query)
    async def run():
        for n in range(4):
            r=await providers.tuniu('hotel','tuniuHotelSearch',{'query':n})
            assert r['source']['credential_slot']==f'TUNIU_API_KEY_{n+1}'
        before=tuniu_pool.remaining_budget()
        r=await providers.tuniu('hotel','tuniuHotelSearch',{'query':0})
        assert r['source']['credential_slot']=='TUNIU_API_KEY_1' and tuniu_pool.remaining_budget()==before
        clock.stamp+=13
        await asyncio.gather(*(providers.tuniu('hotel','tuniuHotelSearch',{'query':4}) for _ in range(3)))
        assert seen==['TUNIU_API_KEY_1','TUNIU_API_KEY_2','TUNIU_API_KEY_3','TUNIU_API_KEY_4','TUNIU_API_KEY_1']
        assert await agent.hotel_query_budget()==155
    asyncio.run(run())


def test_failure_cools_one_account_and_does_not_retry_or_leak_keys(setup,monkeypatch):
    async def query(service,tool,args,credential):
        if credential.slot=='TUNIU_API_KEY_1':raise RuntimeError('HTTP 401 '+credential.key)
        return {'ok':True}
    monkeypatch.setattr(tuniu,'query',query)
    async def run():
        with pytest.raises(providers.DataError) as info:await providers.tuniu('hotel','tuniuHotelSearch',{})
        assert 'synthetic-secret' not in str(info.value)
        r=await providers.tuniu('hotel','tuniuHotelSearch',{})
        assert r['source']['credential_slot']=='TUNIU_API_KEY_2'
    asyncio.run(run())


def test_cancellation_releases_lease_and_invalid_write_tool_never_calls_provider(setup):
    async def run():
        pool=tuniu_pool.AccountPool(config.tuniu_credentials());entered=asyncio.Event()
        async def blocked():
            async with pool.acquire():entered.set();await asyncio.Event().wait()
        task=asyncio.create_task(blocked());await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not pool.busy
        with pytest.raises(providers.DataError,match='白名单'):await providers.tuniu('hotel','tuniuHotelCreateOrder',{})
    asyncio.run(run())


def test_all_blocked_accounts_fail_promptly_and_sdk_group_is_classified(setup):
    _,clock=setup;pool=tuniu_pool.AccountPool(config.tuniu_credentials())
    for c in pool.credentials:pool.cooldown(c,60)
    with pytest.raises(providers.DataError,match='冷却'):pool.reserve(clock.time())
    assert tuniu.failure_kind(ExceptionGroup('SDK failure',[RuntimeError('HTTP 401')]))=='auth'
    assert tuniu.failure_kind(ExceptionGroup('SDK failure',[providers.DataError('授权失败',{'provider_failure':'auth'})]))=='auth'
