"""Resolve evidence-backed web discoveries to actual, selectable map places."""

import asyncio

from app.core.errors import DataError
from app.travel.web_research import name_key


def same_place(city, requested, item):
    def key(name):
        return name_key(name).removeprefix(name_key(city))

    wanted, actual = key(requested), key(item.get("name", ""))
    alias = item.get("alias") or []
    if isinstance(alias, str):
        alias = [alias]
    return (
        wanted == actual
        or wanted in {key(x) for x in alias}
        or (
            actual.startswith(wanted)
            and actual[len(wanted) :] in ("博物院", "博物馆", "风景名胜")
        )
    )


async def resolve(city, places, tool, filter_pois, excluded_ids, excluded_names):
    sem = asyncio.Semaphore(2)
    blocked = {name_key(x).removeprefix(name_key(city)) for x in excluded_names}

    async def one(place):
        if name_key(place["name"]).removeprefix(name_key(city)) in blocked:
            return None
        names = list(dict.fromkeys([place["name"], *place.get("aliases", [])]))
        queries = list(dict.fromkeys([names[0], *names[1:2], name_key(names[0])]))[:2]
        item = None
        for keyword in queries:
            async with sem:
                result = await tool(
                    "search_places",
                    {
                        "city": city,
                        "keywords": keyword,
                        "category": "spot",
                        "page": 1,
                        "page_size": 12,
                    },
                )
            item = next(
                (
                    p
                    for p in filter_pois(result.get("items", []))
                    if (
                        p["id"] not in excluded_ids
                        and any(same_place(city, name, p) for name in names)
                    )
                ),
                None,
            )
            if item:
                break
        if item is None:
            return None
        return {
            **item,
            "web_description": place["description"],
            "recommendation": place["description"],
            "evidence": place["evidence"],
        }

    results = await asyncio.gather(*(one(p) for p in places), return_exceptions=True)
    if results and all(isinstance(row, DataError) for row in results):
        raise DataError("景点资料已找到，地图位置查询暂未成功，请稍后重试。")
    items = {row["id"]: row for row in results if isinstance(row, dict)}
    return list(items.values())
