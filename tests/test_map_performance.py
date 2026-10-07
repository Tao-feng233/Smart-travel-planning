import asyncio
from app import maps

def test_national_basemap_needs_no_trip_markers():
 args=maps.params([],zoom=3,center=(104.1954,35.8617),overlays=False)
 assert args['location']=='104.1954,35.8617' and args['size']=='1024*768'
 assert 'markers' not in args and 'paths' not in args
 assert maps.params([],overlays=False)['zoom']==3

def test_same_map_request_is_coalesced_and_cached(monkeypatch):
 calls=[]
 async def fetch(args):calls.append(args);await asyncio.sleep(.03);return b'map-image','image/png'
 monkeypatch.setattr(maps,'_fetch',fetch);maps.CACHE.clear()
 async def check():
  a,b=await asyncio.gather(maps.image([],zoom=3,overlays=False),maps.image([],zoom=3,overlays=False))
  assert a==b and len(calls)==1
  assert await maps.image([],zoom=3,overlays=False)==a and len(calls)==1
 asyncio.run(check());maps.CACHE.clear()

def test_aborted_waiter_does_not_cancel_shared_map(monkeypatch):
 calls=[]
 async def fetch(args):calls.append(args);await asyncio.sleep(.03);return b'base','image/png'
 monkeypatch.setattr(maps,'_fetch',fetch);maps.CACHE.clear()
 async def check():
  first=asyncio.create_task(maps.image([],overlays=False));second=asyncio.create_task(maps.image([],overlays=False))
  await asyncio.sleep(.01);first.cancel()
  try:await first
  except asyncio.CancelledError:pass
  assert await second==(b'base','image/png') and len(calls)==1
 asyncio.run(check());maps.CACHE.clear()
