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
        return validate_result(name,data)
    try: return validate_result(name,json.loads('\n'.join(x.text for x in result.content if x.type=='text')))
    except (ValueError,AttributeError): raise DataError('MCP 工具响应格式异常') from None

def validate_result(name,data):
    if not isinstance(data,dict):raise DataError('MCP 工具响应应为对象')
    if data.get('status')=='query_failed' and name!='calculate_route':
        raise DataError(data.get('reason') or '数据查询失败，请稍后重试')
    if 'items' in data and not isinstance(data['items'],list):raise DataError('MCP 结果列表格式异常')
    return data
