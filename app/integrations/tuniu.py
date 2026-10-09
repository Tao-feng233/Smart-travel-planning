"""Read-only Tuniu MCP adapter; account rotation belongs to tuniu_pool."""
import asyncio
import hashlib
import json
from jsonschema import validate
from ..storage import RUNTIME,cache_key,cached,put_cache
from ..request_cache import singleflight
from ..providers import DataError,source
from .tuniu_pool import pool
from .tuniu_policy import ALLOW


def cache_id(credential,tool,arguments):
    return cache_key('tuniu:v2:'+credential.account+':'+tool,arguments)


def failure_kind(value):
    context=getattr(value,'context',None)
    if isinstance(context,dict) and context.get('provider_failure'):return context['provider_failure']
    nested=getattr(value,'exceptions',None)
    if nested:
        kinds={failure_kind(error) for error in nested}
        return 'auth' if 'auth' in kinds else 'rate' if 'rate' in kinds else ''
    text=str(value).casefold()
    if any(x in text for x in ('429','rate_limit','too many requests','频率','限流')):return 'rate'
    if any(x in text for x in ('401','403','auth_failed','unauthorized','invalid api','invalid_api','apikey无效','api key无效')):return 'auth'
    return ''


async def query(service,tool,arguments,credential):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with asyncio.timeout(45):
        async with streamablehttp_client('https://openapi.tuniu.cn/hybrid/mcp/'+service,headers={'apiKey':credential.key},timeout=35) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                directory=RUNTIME/'tuniu';directory.mkdir(exist_ok=True)
                path=directory/(credential.account.replace(':','-')+'-'+service+'-schema.json')
                if path.exists():schemas=json.loads(path.read_text(encoding='utf-8'))
                else:
                    schemas=[t.model_dump() for t in (await session.list_tools()).tools]
                    path.write_text(json.dumps(schemas,ensure_ascii=False,indent=2),encoding='utf-8')
                schema=next((t['inputSchema'] for t in schemas if t['name']==tool),None)
                if not schema:raise DataError('实时 MCP schema 中没有所需工具')
                validate(arguments,schema)
                if set(arguments)-set(schema.get('properties',{})):raise DataError('发现供应商未定义的参数')
                result=await session.call_tool(tool,arguments)
                texts=[x.text for x in result.content if getattr(x,'type',None)=='text']
                if result.isError:
                    kind=failure_kind(str(result.structuredContent)+' '.join(texts))
                    raise DataError('途牛账号暂时限流，请稍后再试' if kind=='rate' else '途牛账号授权失败，请检查本机配置' if kind=='auth' else '途牛工具返回查询错误',{'provider_failure':kind})
                data=result.structuredContent
                if data is None:
                    try:data=json.loads('\n'.join(texts))
                    except ValueError:data={'text':'\n'.join(texts)}
                if isinstance(data,dict) and data.get('success') is False:
                    kind=failure_kind(data)
                    raise DataError('途牛查询未成功，已有选择保留',{'provider_failure':kind})
                return data


async def call(service,tool,arguments):
    if tool not in ALLOW.get(service,set()):raise DataError('该工具不在只读查询白名单中')
    scheduler=pool()
    identity=hashlib.sha256('|'.join(c.account for c in scheduler.credentials).encode()).hexdigest()
    async def perform():
        # Cached quotes retain their original account provenance and consume no new quota.
        for credential in scheduler.credentials:
            old=cached(cache_id(credential,tool,arguments))
            if old:return old
        async with scheduler.acquire() as credential:
            try:data=await query(service,tool,arguments,credential)
            except DataError as error:
                kind=(error.context or {}).get('provider_failure')
                if kind:scheduler.cooldown(credential,60 if kind=='rate' else 600)
                raise
            except Exception as error:
                # Inspect locally, but never emit exception strings that may contain credentials.
                kind=failure_kind(error)
                if kind:scheduler.cooldown(credential,60 if kind=='rate' else 600)
                raise DataError('途牛查询失败或超时，请稍后重试') from None
            result={'data':data,'source':source('途牛 MCP','https://open.tuniu.com/mcp/docs/apidoc/mcp/'+service+'MCP.html')}
            result['source']['credential_slot']=credential.slot
            put_cache(cache_id(credential,tool,arguments),result,600)
            return result
    return await singleflight(('tuniu:v2',identity,service,tool,cache_key(tool,arguments)),perform)
