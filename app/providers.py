import asyncio, json, math, time, logging
from datetime import date
import httpx
from jsonschema import validate
from .config import ROOT, setting
from .storage import now, cache_key, cached, put_cache, connect, RUNTIME

# HTTP logs can contain Amap's key query parameter. Never enable URL debug logs.
for _name in ('httpx','httpcore','httpx2','httpcore2'):
    logging.getLogger(_name).setLevel(logging.WARNING)

class DataError(Exception):
    def __init__(self,message,context=None):
        super().__init__(message)
        self.context=context

def source(name, url, fetched=None, kind='查询事实'):
    return {'name':name,'url':url,'queried_at':fetched or now(),'kind':kind}

AMAP_PACING=asyncio.Lock()
AMAP_INFLIGHT=asyncio.Semaphore(2)
AMAP_LAST_REQUEST=0.0

async def amap_slot():
    global AMAP_LAST_REQUEST
    async with AMAP_PACING:
        await asyncio.sleep(max(0,.4-(time.monotonic()-AMAP_LAST_REQUEST)))
        AMAP_LAST_REQUEST=time.monotonic()

async def amap(path, params, ttl=900):
    key=cache_key(path,params)
    old=cached(key)
    if old: return old
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            async with AMAP_INFLIGHT:
                await amap_slot()
                r=await client.get('https://restapi.amap.com'+path,params={**params,'key':setting('AMAP_API_KEY')})
            if r.status_code!=200: raise DataError(f'高德 HTTP {r.status_code}')
            d=r.json()
            if str(d.get('status'))!='1': raise DataError('高德查询失败：'+str(d.get('info','未知错误'))[:100])
    except httpx.HTTPError as e: raise DataError('高德连接失败或超时') from None
    result={'data':d,'source':source('高德地图','https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch')}
    put_cache(key,result,ttl)
    return result

async def search_poi(city, keywords, category='spot',page=1,page_size=6,location=None,radius=5000):
    if not 1<=int(page)<=20 or not 1<=int(page_size)<=25:raise DataError('地点分页参数超出支持范围')
    params={'keywords':keywords,'region':city,'city_limit':'true','page_size':int(page_size),'page_num':int(page),'show_fields':'business,navi,photos,children'}
    if category=='spot': params['types']='110000|140000'
    if category=='food':params['types']='050000'
    if category=='hotel':params['types']='100000'
    path='/v5/place/text'
    if location:
        path='/v5/place/around';params.pop('region',None);params.pop('city_limit',None)
        params.update(location=location,radius=min(10000,max(100,int(radius))))
    r=await amap(path,params)
    items=[]
    for p in r['data'].get('pois',[]):
        code=str(p.get('typecode') or '')
        if category=='spot' and (code.startswith('05') or any(x in p.get('type','') for x in ('餐饮服务','中餐厅'))):continue
        if category=='food' and code and not code.startswith('05'):continue
        if category=='hotel' and code and not code.startswith('10'):continue
        if category=='market' and code.startswith('05'):continue
        items.append(normalize_place(p,r['source'],category))
    return items

def normalize_place(p,provenance,category=None):
    """Search and detail use the same factual fields; empty vendor arrays mean unknown."""
    def value(x):return None if x in (None,'',[]) else x
    b=p.get('business') or {};n=p.get('navi') or {};code=str(p.get('typecode') or '')
    kind=category or ('food' if code.startswith('05') else 'hotel' if code.startswith('10') else 'spot')
    tags=b.get('tag') or ''
    if isinstance(tags,str):tags=[s.strip() for s in tags.replace('；',';').split(';') if s.strip()]
    if not isinstance(tags,list):tags=[]
    return dict(id='amap:'+p['id'],provider_id=p['id'],kind=kind,name=p['name'],address=value(p.get('address')),
                location=value(p.get('location')),entrance=value(n.get('entr_location')),exit=value(n.get('exit_location')),
                citycode=value(p.get('citycode')),city=value(p.get('cityname')),district=value(p.get('adname')),
                rating=value(b.get('rating')),parent_id='amap:'+p['parent'] if p.get('parent') else None,
                children=p.get('children') or [],typecode=code,poi_type=value(p.get('type')),cost=value(b.get('cost')),
                telephone=value(b.get('tel')),alias=value(b.get('alias')),business_area=value(b.get('business_area')),tags=tags,
                opening=value(b.get('opentime_week') or b.get('opentime_today')),
                opening_today=value(b.get('opentime_today')),opening_week=value(b.get('opentime_week')),
                opening_scope='地图当前营业资料，出游日期需核实',
                photos=[x['url'] for x in (p.get('photos') or [])[:8] if isinstance(x,dict) and x.get('url')],
                source=provenance,ticket_price=None,reservation='尚未核实',selected=False)

async def poi_detail(poi_id):
    return await amap('/v5/place/detail',{'id':poi_id,'show_fields':'business,navi,photos,children'})

async def place_details(ids):
    result=await poi_detail('|'.join(i.removeprefix('amap:') for i in ids[:10]))
    rows=[]
    for p in result['data'].get('pois',[]):
        rows.append(normalize_place(p,result['source']))
    return {'items':rows}

async def route(origin, destination, mode, citycode='',destination_citycode=''):
    path={'walking':'walking','driving':'driving','transit':'transit/integrated'}.get(mode)
    if not path: raise DataError('不支持的交通方式')
    if mode=='transit' and not citycode:
        return {'mode':mode,'available':False,'status':'missing_city','reason':'缺少地图城市代码，公交待核实'}
    params={'origin':origin,'destination':destination,'show_fields':'cost,navi,polyline','city1':citycode,'city2':destination_citycode or citycode}
    if mode!='transit': params.pop('city1'); params.pop('city2')
    r=await amap('/v5/direction/'+path,params,300)
    routes=r['data'].get('route',{})
    paths=routes.get('transits' if mode=='transit' else 'paths',[])
    if not paths: return {'mode':mode,'available':False,'status':'no_route','reason':'该方式查询成功，但未返回路线方案','source':r['source']}
    p=paths[0]; cost=p.get('cost') or {}
    duration=cost.get('duration') if cost.get('duration') is not None else p.get('duration')
    if duration in (None,'',[]): return {'mode':mode,'available':False,'status':'incomplete','reason':'接口未提供耗时','source':r['source']}
    details=[];steps=[];polylines=[]
    def add_step(s):
        steps.append({k:s[k] for k in ('instruction','road_name','distance','duration') if s.get(k) is not None})
        if s.get('polyline'):polylines.append(s['polyline'])
    for step in p.get('steps',[]):add_step(step)
    if mode=='transit':
        for seg in p.get('segments',[]):
            for step in (seg.get('walking') or {}).get('steps',[]):add_step(step)
            for bus in (seg.get('bus') or {}).get('buslines',[]):
                details.append(bus.get('name',''))
                steps.append({'instruction':'乘坐 '+bus.get('name','公交'),
                              'from':(bus.get('departure_stop') or {}).get('name'),
                              'to':(bus.get('arrival_stop') or {}).get('name')})
                if bus.get('polyline'):polylines.append(bus['polyline'])
    r['source']['url']='https://developer.amap.com/api/webservice/guide/api/newroute'
    return dict(mode=mode,available=True,status='available',minutes=math.ceil(float(duration)/60),distance=int(float(p.get('distance') or 0)),
                walking_distance=p.get('walking_distance'),fare=cost.get('transit_fee') if mode=='transit' else None,
                details=details,steps=steps,polylines=polylines,source=r['source'],note='查询时路线预计耗时；驾车不含叫车等待，公交按接口整段耗时，不重复加等车时间')

async def weather(location):
    lon,lat=map(float,location.split(','))
    pos=f'{lat:.2f}/{lon:.2f}'
    key=cache_key('weather',pos); old=cached(key)
    if old: return old
    timeout=float(setting('QWEATHER_TIMEOUT_SECONDS','5'))
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r=await c.get('https://'+setting('QWEATHER_API_HOST')+'/weather/v1/daily/'+pos,
                          headers={'X-QW-Api-Key':setting('QWEATHER_API_KEY')},params={'days':10,'localTime':'true','lang':'zh'})
            if r.status_code!=200: raise DataError(f'天气 HTTP {r.status_code}')
            d=r.json()
            if 'days' not in d: raise DataError('天气响应没有预报数据')
            daily=[]
            for day in d['days']:
                b=day.get('daytime',{})
                daily.append(dict(date=day['forecastStartTime'][:10],text=b.get('condition',{}).get('text'),
                                  low=day.get('temperatureMin',{}).get('value'),high=day.get('temperatureMax',{}).get('value'),
                                  rain=b.get('precipitation',{}).get('probability'),wind=b.get('wind',{}).get('scale')))
            alert_status='未查询'; alerts=[]
            try:
                a=await c.get('https://'+setting('QWEATHER_API_HOST')+'/weatheralert/v1/current/'+pos,
                              headers={'X-QW-Api-Key':setting('QWEATHER_API_KEY')},params={'localTime':'true','lang':'zh'})
                ad=a.json()
                if a.status_code==200 and ('alerts' in ad or ad.get('metadata',{}).get('zeroResult')):
                    alerts=ad.get('alerts',[]); alert_status='当前预警查询成功'
                else: alert_status='当前预警查询失败，不等于无预警'
            except (httpx.HTTPError,ValueError): alert_status='当前预警连接失败，不等于无预警'
    except httpx.HTTPError: raise DataError('天气查询超时或连接失败') from None
    result=dict(days=daily,alerts=alerts,alert_status=alert_status,attributions=d.get('metadata',{}).get('attributions',[]),
                source=source('和风天气','https://dev.qweather.com/docs/api/weather/weather-daily-forecast/'))
    put_cache(key,result,900)
    return result

ALLOW={'hotel':{'tuniuHotelSearch','tuniuHotelDetail'},'train':{'searchLowestPriceTrain','queryTrainDetail'},
       'flight':{'searchLowestPriceFlight','multiCabinDetails'},'ticket':{'query_cheapest_tickets'}}
TUNIU_LOCK=asyncio.Lock()

async def tuniu(service,tool,arguments):
    if tool not in ALLOW.get(service,set()): raise DataError('该工具不在只读查询白名单中')
    key=cache_key('tuniu:'+tool,arguments)
    old=cached(key)
    if old: return old
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with TUNIU_LOCK:
        old=cached(key)
        if old: return old
        with connect() as c:
            day_start=time.time()-86400
            count=c.execute('SELECT COUNT(*) FROM calls WHERE provider=? AND time>?',('tuniu',day_start)).fetchone()[0]
            last=c.execute('SELECT MAX(time) FROM calls WHERE provider=?',('tuniu',)).fetchone()[0]
        if count>=int(setting('TUNIU_DAILY_LIMIT','40')): raise DataError('本项目的途牛查询预算已用完，请稍后再试')
        if last and time.time()-last<13: await asyncio.sleep(13-(time.time()-last))
        with connect() as c: c.execute('INSERT INTO calls VALUES(?,?)',('tuniu',time.time()))
        try:
            async with asyncio.timeout(45):
                async with streamablehttp_client('https://openapi.tuniu.cn/hybrid/mcp/'+service,headers={'apiKey':setting('TUNIU_API_KEY')},timeout=35) as (read,write,_):
                    async with ClientSession(read,write) as s:
                        await s.initialize()
                        f=RUNTIME/('tuniu-'+service+'-schema.json')
                        if f.exists(): schemas=json.loads(f.read_text(encoding='utf-8'))
                        else:
                            schemas=[t.model_dump() for t in (await s.list_tools()).tools]
                            f.write_text(json.dumps(schemas,ensure_ascii=False,indent=2),encoding='utf-8')
                        schema=next((t['inputSchema'] for t in schemas if t['name']==tool),None)
                        if not schema: raise DataError('实时 MCP schema 中没有所需工具')
                        validate(arguments,schema)
                        if set(arguments)-set(schema.get('properties',{})): raise DataError('发现供应商未定义的参数')
                        r=await s.call_tool(tool,arguments)
                        if r.isError: raise DataError('途牛工具返回查询错误')
                        data=r.structuredContent
                        texts=[x.text for x in r.content if getattr(x,'type',None)=='text']
                        if data is None:
                            try: data=json.loads('\n'.join(texts))
                            except ValueError: data={'text':'\n'.join(texts)}
        except DataError: raise
        except Exception: raise DataError('途牛查询失败或超时，请稍后重试') from None
    result={'data':data,'source':source('途牛 MCP','https://open.tuniu.com/mcp/docs/apidoc/mcp/'+service+'MCP.html')}
    put_cache(key,result,600)
    return result

async def llm(messages, tools=None, json_mode=False, max_tokens=2200):
    body={'model':setting('LLM_MODEL','deepseek-flash'),'messages':messages,'max_tokens':max_tokens,
          'thinking':{'type':'disabled'},'temperature':0.3}
    if tools: body.update(tools=tools,tool_choice='required')
    if json_mode: body['response_format']={'type':'json_object'}
    try:
        async with httpx.AsyncClient(timeout=100) as c:
            r=await c.post(setting('LLM_BASE_URL').rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+setting('LLM_API_KEY')},json=body)
            if r.status_code!=200: raise DataError(f'大模型请求失败，HTTP {r.status_code}')
            data=r.json()
            return data['choices'][0]['message'],data.get('usage',{})
    except httpx.HTTPError: raise DataError('大模型连接失败或响应超时') from None
async def llm_stream(messages,on_delta,max_tokens=1600):
    body={'model':setting('LLM_MODEL','deepseek-flash'),'messages':messages,'max_tokens':max_tokens,
          'thinking':{'type':'disabled'},'temperature':0.3,'stream':True,'stream_options':{'include_usage':True}}
    text='';usage={};finished=False
    try:
        async with httpx.AsyncClient(timeout=100) as c:
            async with c.stream('POST',setting('LLM_BASE_URL').rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+setting('LLM_API_KEY')},json=body) as r:
                if r.status_code!=200:raise DataError(f'大模型请求失败，HTTP {r.status_code}')
                async for line in r.aiter_lines():
                    if not line.startswith('data:'):continue
                    payload=line[5:].strip()
                    if payload=='[DONE]':finished=True;break
                    data=json.loads(payload);usage=data.get('usage') or usage
                    for choice in data.get('choices',[]):
                        chunk=choice.get('delta',{}).get('content')
                        if chunk:text+=chunk;on_delta(chunk)
                        if choice.get('finish_reason')=='length':raise DataError('回复达到长度限制，请重新发起更具体的问题。')
        if not finished or not text:raise DataError('流式回复中断，请重试。')
        return text,usage
    except (httpx.HTTPError,ValueError):raise DataError('流式回复连接失败或中断，请重试。') from None
