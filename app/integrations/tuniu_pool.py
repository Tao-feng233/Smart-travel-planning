"""Round-robin account leases with durable quota reservations, never raw keys in storage."""
import asyncio
import time
import weakref
from contextlib import asynccontextmanager
from ..config import setting,tuniu_credentials
from ..storage import connect
from ..providers import DataError

INTERVAL=13.0
POOLS=weakref.WeakKeyDictionary()


def daily_limit():
    try:return max(1,min(50,int(setting('TUNIU_DAILY_LIMIT','40'))))
    except ValueError:return 40


def buckets(credential,credentials):
    values=[credential.account]
    # Retain old usage when upgrading, rather than resetting the original account's quota.
    legacy=setting('TUNIU_API_KEY')
    prior=next((x.account for x in credentials if legacy and x.key==legacy),credentials[0].account)
    if credential.account==prior and 'tuniu' not in values:values.append('tuniu')
    return values


def usage(db,credential,credentials,stamp):
    tags=buckets(credential,credentials);marks=','.join('?' for _ in tags)
    row=db.execute(f'SELECT COUNT(*),MAX(time) FROM calls WHERE provider IN ({marks}) AND time>?',(*tags,stamp-86400)).fetchone()
    blocked=db.execute('SELECT MAX(time) FROM calls WHERE provider=?',('tuniu:block:'+credential.account,)).fetchone()[0] or 0
    return row[0],row[1] or 0,blocked


def remaining_budget():
    credentials=tuniu_credentials()
    if not credentials:return 0
    with connect() as db:
        stamp=time.time();groups={c.account:c for c in credentials}
        return sum(max(0,daily_limit()-usage(db,c,credentials,stamp)[0]) for c in groups.values())


class AccountPool:
    def __init__(self,credentials):
        self.credentials=credentials;self.cursor=0;self.busy=set();self.lock=asyncio.Lock()

    def reserve(self,stamp):
        waits=[];has_budget=False
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for offset in range(len(self.credentials)):
                i=(self.cursor+offset)%len(self.credentials);credential=self.credentials[i]
                count,last,blocked=usage(db,credential,self.credentials,stamp)
                if count>=daily_limit():continue
                has_budget=True
                wait=max(0,last+INTERVAL-stamp,blocked-stamp)
                if credential.account in self.busy:wait=max(wait,.1)
                if wait:waits.append(wait);continue
                db.execute('INSERT INTO calls VALUES(?,?)',(credential.account,stamp))
                self.cursor=(i+1)%len(self.credentials);self.busy.add(credential.account)
                return credential,0
        if not has_budget:raise DataError('所有已配置途牛账号的项目查询预算已用完，请稍后再试。')
        if waits and min(waits)>INTERVAL:raise DataError('可用途牛账号暂时处于限流或授权异常冷却，请稍后重试或检查配置。')
        return None,min(waits or [.1])

    @asynccontextmanager
    async def acquire(self):
        credential=None
        while credential is None:
            async with self.lock:credential,wait=self.reserve(time.time())
            if credential is None:await asyncio.sleep(min(wait,1.0))
        try:yield credential
        finally:self.busy.discard(credential.account)

    def cooldown(self,credential,seconds):
        with connect() as db:db.execute('INSERT INTO calls VALUES(?,?)',('tuniu:block:'+credential.account,time.time()+seconds))


def pool():
    credentials=tuniu_credentials()
    if not credentials:raise DataError('请在本机 .env 配置 TUNIU_API_KEY_1 至 TUNIU_API_KEY_4，或原来的 TUNIU_API_KEY。')
    loop=asyncio.get_running_loop();value=POOLS.get(loop)
    if value is None or value.credentials!=credentials:value=AccountPool(credentials);POOLS[loop]=value
    return value
