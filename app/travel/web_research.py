"""Model-controlled web searches with bounded calls and evidence-bound results."""

import json
import re

from app.core.errors import DataError
from app.prompts.web_research import WEB_RESEARCH

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_travel_web",
        "description": "通过Tavily搜索官方旅游资料，或页面点赞至少10000的体验文章。返回来源、正文与时间；不查询实时价格和库存。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "城市与主题或具体地点的搜索词",
                },
                "source_type": {"type": "string", "enum": ["official", "popular"]},
            },
            "required": ["query", "source_type"],
            "additionalProperties": False,
        },
    },
}


def name_key(name):
    return re.sub(r"[\W_]|风景名胜区|风景区|景区|旅游区|公园|市$", "", str(name))


def grounded_places(value, documents, city):
    by_id = {x["id"]: x for x in documents}
    places = []
    seen = set()
    rows = value.get("places", [])
    if not isinstance(rows, list):
        return []
    for row in rows[:24]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()[:80]
        key = name_key(name)
        evidence_ids = row.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            continue
        refs = [by_id[x] for x in evidence_ids if isinstance(x, str) and x in by_id]
        short = key.removeprefix(name_key(city)) if city else key
        if (
            len(short) < 2
            or key in seen
            or not any(
                short in name_key(ref["title"] + " " + ref["text"]) for ref in refs
            )
        ):
            continue
        seen.add(key)
        aliases = row.get("aliases") or []
        aliases = (
            [
                x
                for x in aliases[:4]
                if isinstance(x, str)
                and 2 <= len(x) <= 80
                and any(
                    name_key(x).removeprefix(name_key(city))
                    in name_key(ref["title"] + " " + ref["text"])
                    for ref in refs
                )
            ]
            if isinstance(aliases, list)
            else []
        )
        places.append(
            {
                "name": name,
                "city": city or str(row.get("city") or name),
                "aliases": aliases,
                "description": str(row.get("description") or "")[:450],
                "evidence": refs,
            }
        )
    return places


async def research(
    requirements, task, model, tool, progress, *, city="", excluded=None
):
    messages = [
        {"role": "system", "content": WEB_RESEARCH},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "requirements": requirements,
                    "task": task,
                    "city": city,
                    "excluded_places": list(excluded or [])[:80],
                },
                ensure_ascii=False,
            ),
        },
    ]
    documents, searches, seen_queries, failures = {}, 0, set(), []
    successful_searches = 0
    for _ in range(5):
        remaining = searches < 3
        response, _usage = await model(
            messages,
            tools=[SEARCH_TOOL] if remaining else None,
            json_mode=not remaining,
            max_tokens=3500,
            label="web_research",
        )
        calls = response.get("tool_calls") or []
        if not calls:
            if not searches:
                messages.append(
                    {
                        "role": "user",
                        "content": "必须先调用搜索工具取得实际依据，再返回结果。",
                    }
                )
                continue
            try:
                value = json.loads(response.get("content") or "")
                if not isinstance(value, dict):
                    raise ValueError()
            except (ValueError, TypeError):
                raise DataError("搜索已完成，模型未能整理可用结果，请重试。") from None
            docs = list(documents.values())
            if not docs and failures and not successful_searches:
                raise DataError("旅游搜索暂未成功：" + failures[-1])
            return {
                "places": grounded_places(value, docs, city),
                "guides": docs,
                "summary": str(value.get("summary") or ""),
                "search_calls": searches,
            }
        messages.append(response)
        for index, call in enumerate(calls):
            function = call.get("function") or {}
            result = {"items": [], "status": "query_failed"}
            try:
                if function.get("name") != "search_travel_web" or searches >= 3:
                    raise DataError(
                        "本轮仅允许旅游资料搜索，搜索预算已用完时请综合已有依据。"
                    )
                args = json.loads(function.get("arguments") or "{}")
                if not isinstance(args, dict) or set(args) - {"query", "source_type"}:
                    raise DataError("搜索参数无效。")
                query = str(args.get("query") or "").strip()
                source_type = args.get("source_type", "official")
                identity = (query, source_type)
                if identity in seen_queries:
                    raise DataError("相同查询已经执行，请使用现有资料或更换查询方向。")
                seen_queries.add(identity)
                searches += 1
                progress("正在搜索旅游资料（" + str(searches) + "/3）")
                result = await tool(
                    "search_travel_web",
                    {
                        "query": query,
                        "city": city,
                        "source_type": source_type,
                        "max_results": 6,
                    },
                )
                if result.get("status") == "query_failed":
                    raise DataError(result.get("reason") or "搜索服务查询失败。")
                successful_searches += 1
                for item in result.get("items", []):
                    documents[item["id"]] = item
            except (DataError, ValueError, TypeError) as error:
                result["reason"] = (
                    str(error) if isinstance(error, DataError) else "搜索参数无效。"
                )
                if function.get("name") == "search_travel_web" and searches:
                    failures.append(result["reason"])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"search-{searches}-{index}",
                    "content": json.dumps(
                        {
                            **result,
                            "items": [
                                {**item, "text": item["text"][:2400]}
                                for item in result.get("items", [])
                            ],
                        },
                        ensure_ascii=False,
                    ),
                }
            )
    raise DataError("本轮旅游搜索已达到处理上限，请缩小搜索主题后重试。")
