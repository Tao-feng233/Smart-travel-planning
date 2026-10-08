"""Per-event-loop HTTP pools and coalesced identical in-flight requests."""
import asyncio
import copy
from contextlib import asynccontextmanager

import httpx

_clients={}
_client_locks={}
_pending={}
metrics={'started':0,'joined':0,'http_clients':0}


@asynccontextmanager
async def http_client(timeout):
    loop=asyncio.get_running_loop();key=(loop,httpx.AsyncClient,timeout)
    pair=_clients.get(key)
    if pair is None:
        async with _client_locks.setdefault(key,asyncio.Lock()):
            pair=_clients.get(key)
            if pair is None:
                owner=httpx.AsyncClient(timeout=timeout);client=await owner.__aenter__()
                pair=(owner,client);_clients[key]=pair;metrics['http_clients']+=1
    yield pair[1]


async def singleflight(key,factory):
    identity=(asyncio.get_running_loop(),key);task=_pending.get(identity)
    if task is None:
        metrics['started']+=1;task=asyncio.create_task(factory());_pending[identity]=task
        def done(value):
            if _pending.get(identity) is value:_pending.pop(identity,None)
            if not value.cancelled():value.exception()
        task.add_done_callback(done)
    else:metrics['joined']+=1
    # A cancelled UI caller cannot cancel another caller's shared supplier work.
    return copy.deepcopy(await asyncio.shield(task))


async def close():
    loop=asyncio.get_running_loop()
    tasks=[task for (owner,_),task in list(_pending.items()) if owner is loop]
    for task in tasks:task.cancel()
    if tasks:await asyncio.gather(*tasks,return_exceptions=True)
    for key,pair in list(_clients.items()):
        if key[0] is not loop:continue
        _clients.pop(key,None)
        _client_locks.pop(key,None)
        await pair[0].__aexit__(None,None,None)
