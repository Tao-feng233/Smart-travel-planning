"""Authenticated map prototype using saved POI coordinates and Amap's static API."""
import math
import asyncio,time,json
from collections import OrderedDict
import httpx
from .config import setting
from .providers import DataError

CACHE=OrderedDict();INFLIGHT={};CLIENT=None;CLIENT_LOOP=None

def coordinate(p):
 try:
  x,y=map(float,p.get('location','').split(','))
  return (x,y) if math.isfinite(x) and math.isfinite(y) and -180<=x<=180 and -85<=y<=85 else None
 except (ValueError,AttributeError):return None

def points(w,dt='',focus=''):
 catalog=w['catalog'];items=[]
 if focus:
  p=catalog.get(focus)
  return [p] if p and coordinate(p) else []
 if dt:
  day=next((d for d in (w.get('plan') or {}).get('days',[]) if d['date']==dt),None)
  if day and not w['plan'].get('stale'):
   for e in day.get('events',[]):
    p=catalog.get(e.get('candidate_id')) or e.get('food')
    if p and coordinate(p):items.append(p)
  else:
   from .visits import meal_refs
   items=meal_refs(w,dt,'dinner')
 else:items=[catalog[i] for i in w.get('selected_spots',[]) if i in catalog]
 if not items and not dt:items=[p for p in catalog.values() if p.get('kind')=='spot'][:12]
 if w.get('hotel') and coordinate(w['hotel']):items=[w['hotel']]+items
 if not dt:
  items+=[catalog[c['food_id']] for c in w.get('meal_choices',{}).values() if c.get('mode')=='chosen' and c.get('food_id') in catalog]
 result=[];seen=set()
 for p in items:
  if p['id'] not in seen and coordinate(p):result.append(p);seen.add(p['id'])
 return result[:10]

def viewport(coords):
 xs=[c[0]/360+.5 for c in coords]
 ys=[.5-math.log((1+math.sin(math.radians(c[1])))/(1-math.sin(math.radians(c[1]))))/(4*math.pi) for c in coords]
 center=(round(((min(xs)+max(xs))/2-.5)*360,6),round(math.degrees(math.atan(math.sinh(math.pi*(1-2*(min(ys)+max(ys))/2)))),6))
 if len(coords)==1:return center,15
 span_x=max(xs)-min(xs);span_y=max(ys)-min(ys)
 # Reserve space for markers; use the logical dimensions of a scale=1 map.
 levels=[math.log2(size/(256*span)) for size,span in ((660,span_x),(320,span_y)) if span>0]
 return center,max(1,min(17,math.floor(min(levels)))) if levels else 15

def params(items,ordered=False,zoom=None,center=None,overlays=True):
 if not items and overlays:raise DataError('这些地点暂无可用坐标。')
 coords=[coordinate(p) for p in items];coords=[c for c in coords if c][:10]
 if not coords and overlays:raise DataError('这些地点暂无可用坐标。')
 values=['%s,%s'%c for c in coords]
 # Let Amap fit markers when more than one point is present.
 fitted,fit=viewport(coords) if coords else ((104.1954,35.8617),3)
 if center is not None:
  try:center=coordinate({'location':','.join(map(str,center))})
  except TypeError:center=None
  if center is None:raise DataError('地图中心坐标无效。')
 else:center=fitted
 if zoom is not None and (not isinstance(zoom,int) or not 1<=zoom<=17):raise DataError('地图缩放级别应在1至17之间。')
 result={'size':'800*440' if overlays else '1024*768','scale':1,'location':'%s,%s'%center,'zoom':fit if zoom is None else zoom}
 if overlays:result['markers']='|'.join('mid,0x4565bb,'+chr(65+i)+':'+v for i,v in enumerate(values))
 if overlays and ordered and len(values)>1:result['paths']='3,0x4565bb,0.7,,: '+';'.join(values);result['paths']=result['paths'].replace(': ',':')
 return result

async def _fetch(args):
 global CLIENT,CLIENT_LOOP
 loop=asyncio.get_running_loop()
 if CLIENT is None or CLIENT_LOOP is not loop or CLIENT.is_closed:
  CLIENT=httpx.AsyncClient(timeout=12,limits=httpx.Limits(max_connections=6,max_keepalive_connections=6));CLIENT_LOOP=loop
 try:
  r=await CLIENT.get('https://restapi.amap.com/v3/staticmap',params={**args,'key':setting('AMAP_API_KEY')})
  mime=r.headers.get('content-type','').split(';')[0]
  if r.status_code!=200 or mime not in ('image/png','image/jpeg') or len(r.content)>6_000_000:raise DataError('底图暂未加载成功，可继续操作或重试。')
  return r.content,mime
 except httpx.HTTPError:raise DataError('底图更新超时，可继续操作或重试。') from None

async def _cached_fetch(key,args):
 data,mime=await _fetch(args);CACHE[key]=(time.monotonic()+600,data,mime);CACHE.move_to_end(key)
 while len(CACHE)>80 or sum(len(v[1]) for v in CACHE.values())>40_000_000:CACHE.popitem(last=False)
 return data,mime

async def image(items,ordered=False,zoom=None,center=None,overlays=True):
 args=params(items,ordered,zoom,center,overlays);key=json.dumps(args,sort_keys=True)
 old=CACHE.get(key)
 if old and old[0]>time.monotonic():CACHE.move_to_end(key);return old[1],old[2]
 task=INFLIGHT.get(key)
 if task is None:
  task=asyncio.create_task(_cached_fetch(key,args));INFLIGHT[key]=task
  def done(t):
   INFLIGHT.pop(key,None)
   if not t.cancelled():t.exception()
  task.add_done_callback(done)
 return await asyncio.shield(task)

async def close():
 global CLIENT,CLIENT_LOOP
 pending=list(INFLIGHT.values())
 for task in pending:task.cancel()
 if pending:await asyncio.gather(*pending,return_exceptions=True)
 INFLIGHT.clear()
 if CLIENT and not CLIENT.is_closed:await CLIENT.aclose()
 CLIENT=None;CLIENT_LOOP=None
