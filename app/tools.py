import json
from .providers import DataError

SESSION=None

async def local_tool(name,arguments):
    if SESSION is None: raise DataError('本地 MCP 工具服务尚未连接')
    result=await SESSION.call_tool(name,arguments)
    if result.isError: raise DataError('本地数据工具查询失败，请稍后重试')
    data=result.structuredContent
    if data is not None:
        # SDK wraps some primitive return types; our tools all return dicts.
        return data
    try: return json.loads('\n'.join(x.text for x in result.content if x.type=='text'))
    except (ValueError,AttributeError): raise DataError('MCP 工具响应格式异常') from None
