"""Minimal read-only provider check. Never print credentials or request URLs."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import ROOT, setting

OUT = ROOT / 'data/runtime'
OUT.mkdir(parents=True, exist_ok=True)

async def main():
    result = {}
    async with httpx.AsyncClient(timeout=20) as c:
        checks = {
            'amap': ('https://restapi.amap.com/v5/place/text', {'params': {'key':setting('AMAP_API_KEY'),'keywords':'栈桥','region':'青岛','city_limit':'true','show_fields':'business,navi','page_size':2}}),
            'weather': ('https://' + setting('QWEATHER_API_HOST') + '/weather/v1/daily/36.07/120.38', {'headers': {'X-QW-Api-Key': setting('QWEATHER_API_KEY')}, 'params': {'days':3,'localTime':'true','lang':'zh'}}),
            'llm': (setting('LLM_BASE_URL')+'/models', {'headers': {'Authorization':'Bearer '+setting('LLM_API_KEY')}})
        }
        for name,(url,kwargs) in checks.items():
            try:
                r = await c.get(url,**kwargs)
                d = r.json()
                result[name]={'http':r.status_code,'keys':list(d)[:12]}
                if name=='amap':
                    result[name].update(status=d.get('status'),info=d.get('info'),count=len(d.get('pois',[])))
                    if d.get('pois'): result[name]['sample']=d['pois'][0]
                if name=='weather': result[name]['sample']=d.get('days',[None])[0]; result[name]['error']=d.get('error')
                if name=='llm': result[name]['models']=[v.get('id') for v in d.get('data',[])]; result[name]['configured_model_available']=setting('LLM_MODEL') in result[name]['models']
            except Exception as e: result[name]={'error_type':type(e).__name__}
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    for service in ('hotel','train','flight','ticket'):
        try:
            async with asyncio.timeout(30):
                async with streamablehttp_client('https://openapi.tuniu.cn/hybrid/mcp/'+service,headers={'apiKey':setting('TUNIU_API_KEY')},timeout=20) as (read,write,_):
                    async with ClientSession(read,write) as s:
                        await s.initialize()
                        tools=await s.list_tools()
                        schemas=[t.model_dump() for t in tools.tools]
                        (OUT/('tuniu-'+service+'-schema.json')).write_text(json.dumps(schemas,ensure_ascii=False,indent=2),encoding='utf-8')
                        result['tuniu_'+service]={'tools':[t.name for t in tools.tools]}
        except Exception as e: result['tuniu_'+service]={'error_type':type(e).__name__}
    (OUT/'provider-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for n,v in result.items(): print(n,json.dumps({k:x for k,x in v.items() if k!='sample'},ensure_ascii=False))

asyncio.run(main())
