import json
from app.core.errors import DataError

SESSION = None


async def local_tool(name, arguments):
    if SESSION is None:
        raise DataError("本地 MCP 工具服务尚未连接")
    result = await SESSION.call_tool(name, arguments)
    if result.isError:
        # MCP 把工具的 DataError 折成 isError=True + 文本。以前这里一律换成
        # 「查询失败，请稍后重试」，把「这个城市没数据」说成了「系统坏了」。
        # 有原文就透传原文，没有才回落到泛化提示。
        detail = " ".join(
            str(x.text).strip()
            for x in result.content or []
            if getattr(x, "type", None) == "text" and getattr(x, "text", None)
        ).strip()
        raise DataError(detail[:200] or "本地数据工具查询失败，请稍后重试")
    data = result.structuredContent
    if data is not None:
        # SDK wraps some primitive return types; our tools all return dicts.
        return validate_result(name, data)
    try:
        return validate_result(
            name,
            json.loads("\n".join(x.text for x in result.content if x.type == "text")),
        )
    except (ValueError, AttributeError):
        raise DataError("MCP 工具响应格式异常") from None


def validate_result(name, data):
    if not isinstance(data, dict):
        raise DataError("MCP 工具响应应为对象")
    if data.get("status") == "query_failed" and name != "calculate_route":
        raise DataError(data.get("reason") or "数据查询失败，请稍后重试")
    if "items" in data and not isinstance(data["items"], list):
        raise DataError("MCP 结果列表格式异常")
    return data
