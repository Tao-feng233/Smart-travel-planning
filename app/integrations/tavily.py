"""Bounded Tavily Search API adapter with admitted, source-linked evidence."""

import asyncio
import hashlib
import time

import httpx

from app.core.config import setting
from app.core.errors import DataError
from app.integrations.request_cache import http_client, singleflight
from app.integrations.web_sources import POPULAR_DOMAINS, evidence, official_domains
from app.integrations import trust_score
from app.persistence import storage

INFLIGHT = asyncio.Semaphore(2)


async def search(query, city="", source_type="official", max_results=6):
    if not isinstance(query, str) or not query.strip() or len(query) > 400:
        raise DataError("请提供不超过400字的旅游搜索词。")
    if source_type not in ("official", "popular"):
        raise DataError("搜索来源应为官方信息或高赞平台文章。")
    if not isinstance(max_results, int) or not 1 <= max_results <= 10:
        raise DataError("搜索结果数量应为1至10。")
    key = setting("TAVILY_API_KEY")
    if not key:
        raise DataError("尚未配置旅游搜索服务，请检查 TAVILY_API_KEY。")
    domains = official_domains() if source_type == "official" else list(POPULAR_DOMAINS)
    query = query.strip()
    if city and city not in query:
        query = city + " " + query
    body = {
        "query": query,
        "topic": "general",
        "search_depth": "advanced",
        "max_results": max_results,
        "include_domains": domains,
        "include_answer": False,
        "include_raw_content": "markdown",
        "include_published_date": True,
        "country": "china",
    }
    identity = storage.cache_key(
        "tavily:v1",
        {
            "request": body,
            "credential": hashlib.sha256(key.encode()).hexdigest()[:16],
            "policy": "official-or-page-likes-10000:v1",
        },
    )

    async def perform():
        old = storage.cached(identity)
        if old:
            return old
        started = time.monotonic()
        try:
            async with INFLIGHT:
                async with http_client(20) as client:
                    response = await client.post(
                        "https://api.tavily.com/search",
                        json=body,
                        headers={"Authorization": "Bearer " + key},
                    )
            if response.status_code != 200:
                reason = {
                    401: "搜索服务密钥无效",
                    429: "搜索服务请求过多，请稍后重试",
                    432: "搜索服务额度不足",
                    433: "搜索服务额度不足",
                }.get(response.status_code, "旅游搜索服务暂时不可用")
                raise DataError(reason)
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise DataError("旅游搜索服务返回格式异常。")
        except (httpx.HTTPError, ValueError):
            raise DataError("旅游搜索超时或响应异常，请稍后重试。") from None
        queried_at = storage.now()
        items, rejected = [], {}
        for row in data["results"]:
            if not isinstance(row, dict):
                continue
            item, reason = evidence(row, city, queried_at, source_type)
            if item:
                items.append(item)
            else:
                rejected[reason] = rejected.get(reason, 0) + 1
        trust_score.enrich(items)
        result = {
            "items": items,
            "status": "available" if items else "empty",
            "query_conditions": {
                "query": query,
                "city": city,
                "source_type": source_type,
            },
            "checked_at": queried_at,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "rejected_counts": rejected,
            "note": "官方来源优先；非官方文章须有页面可核实点赞数至少10000。相关性分数不代表点赞或事实可信度。",
        }
        storage.put_cache(identity, result, 600)
        return result

    return await singleflight(("tavily", identity), perform)
