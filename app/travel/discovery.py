"""Bounded, source-backed destination discovery and distinct POI recommendation pages."""

import re, math
from app.integrations.tools import local_tool
from app.core.errors import DataError
from app.integrations.contracts import guide_conditions

PAGE_SIZE = 4
MAX_RECOMMENDATIONS = 24


def destinations():
    from app.knowledge.coverage import snapshot

    return list(snapshot()["cities"].values())


def classic_names(city):
    return next((d["highlights"] for d in destinations() if d["name"] in city), [])


def clean_name(name):
    return re.sub(r"[（(].*?[）)]|风景区|景区|公园|\s", "", name)


def main_pois(items):
    result = []
    seen = set()
    for p in items:
        name = p.get("name", "")
        if (
            p.get("kind") != "spot"
            or str(p.get("typecode") or "").startswith("05")
            or any(x in name for x in ("餐厅", "海鲜火锅", "海鲜自助"))
        ):
            continue
        if any(
            x in name
            for x in (
                "停车场",
                "售票处",
                "售票点",
                "检票",
                "出入口",
                "游客中心",
                "服务中心",
                "公共厕所",
                "卫生间",
                "电动车充电",
            )
        ):
            continue
        if re.search(r"(?:东|西|南|北|正|入口|出口)门(?:$|[（(])", name):
            continue
        key = clean_name(name)
        if p["id"] in seen or ("name", key) in seen:
            continue
        seen.add(p["id"])
        seen.add(("name", key))
        result.append(p)
    return result


def visible(w):
    search = w.get("spot_search") or {}
    rejected = set(w.get("rejected_spots", []))
    return [
        cid
        for cid in search.get("ids", [])[:MAX_RECOMMENDATIONS]
        if cid not in rejected and cid in w["catalog"]
    ]


def page_info(w):
    search = w.get("spot_search") or {}
    grouped = groups(w)
    page = max(
        1, min(int(search.get("page", 1)), max(1, math.ceil(len(grouped) / PAGE_SIZE)))
    )
    displayed = grouped[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    return {
        "page": page,
        "pages": max(1, math.ceil(len(grouped) / PAGE_SIZE)),
        "ids": list(
            dict.fromkeys(
                i
                for g in displayed
                for i in ([g["parent_id"]] if g.get("parent_id") else []) + g["ids"]
                if i in w["catalog"]
            )
        ),
        "has_more": False,
    }


def groups(w):
    from app.travel.spot_hierarchy import ancestors

    catalog = w.get("catalog", {})
    ids = visible(w)
    result = []
    by = {}
    prefixes = {}
    for cid in ids:
        p = catalog[cid]
        name = p.get("name", "")
        parts = re.split("[·•]", name, maxsplit=1)
        if len(parts) == 2 and len(parts[0]) >= 3:
            prefixes.setdefault(parts[0], []).append(cid)
    for cid in ids:
        p = catalog[cid]
        chain = ancestors(catalog, cid)
        parent = chain[-1] if chain else None
        name = p.get("name", "")
        prefix = re.split("[·•]", name, maxsplit=1)[0]
        if parent:
            key = parent
            title = catalog.get(parent, {}).get("name") or prefix
            basis = "地图父子关系"
        elif len(prefixes.get(prefix, [])) >= 2:
            key = "name:" + prefix
            title = prefix
            basis = "名称关联，所属关系待核实"
        else:
            key = cid
            title = name
            basis = None
        if key not in by:
            item = {
                "key": key,
                "title": title,
                "parent_id": parent
                if parent in catalog
                else cid
                if not basis
                else None,
                "ids": [],
                "basis": basis,
            }
            by[key] = item
            result.append(item)
        by[key]["ids"].append(cid)
        if parent:
            by[key]["basis"] = "地图父子关系"
    for g in result:
        g["ids"] = list(dict.fromkeys(g["ids"]))
        if g["parent_id"] in w.get("rejected_spots", []):
            g["parent_id"] = None
    return result


def recommendation_minimum(w, args):
    try:
        days = max(1, int(w["requirements"].get("days") or 2))
    except (TypeError, ValueError):
        days = 2
    try:
        requested = max(0, int(args.get("recommend_count") or 0))
    except (TypeError, ValueError):
        requested = 0
    return min(
        MAX_RECOMMENDATIONS, max(4 if args.get("expand_spots") else days * 2, requested)
    )


async def search(w, args, progress, recommend):
    from app.knowledge.coverage import require_place
    from app.knowledge.web_fallback import require_city_or_web
    from app.travel import spot_search
    from app.travel.locations import ready_candidates

    city = w["requirements"]["city"]
    origin = require_city_or_web(w, city)
    # 联网准入的城市没有本地景点词条，无法核对具体景点；不猜测、直接跳过该检查。
    if args.get("requested_place") and origin != "web":
        require_place(city, args["requested_place"])
    displayed = page_info(w)["ids"] if args.get("reject_current") else []
    query = spot_search.SpotSearch.prepare(
        w, args, classic_names(city), displayed, recommendation_minimum(w, args)
    )
    batch = await spot_search.collect(
        w, query, progress, local_tool, main_pois, MAX_RECOMMENDATIONS
    )
    if not batch.items:
        if query.previous.get("city") == city and query.previous.get("ids"):
            w["spot_search"] = query.previous
        return query.unavailable_message()
    items, location_excluded = await ready_candidates(w, batch.items, local_tool)
    if not items:
        return "本次景点候选尚未核对到有效坐标，暂不列入推荐。可以更换搜索条件或稍后重试；已有选择保留。"
    items = spot_search.stage_candidates(w, query, items[:MAX_RECOMMENDATIONS])
    progress("基础景点资料已到达，正在补充推荐与通行核对")
    for item in items:
        item["classic"] = any(
            clean_name(name) == clean_name(item["name"]) for name in query.classic
        )
        if item["classic"]:
            item["discovery_label"] = "城市代表景点"
    guides = (
        await local_tool(
            "retrieve_guides",
            guide_conditions(
                city,
                " ".join(item["name"] for item in items) + " 游览 特色",
                w["requirements"],
            ),
        )
    )["items"]
    progress("正在按旅行偏好比较推荐顺序")
    summary = await recommend(w, items, query.recommendation_task(len(items)), guides)
    spot_search.rank(items, args.get("prefer_known"))
    items, excluded = await spot_search.screen_routes(
        w, items[:MAX_RECOMMENDATIONS], progress
    )
    if not items:
        spot_search.restore_candidates(w, query)
        return "新候选未通过通行核对，原有候选与选择保留。可以调整查询条件后重试。"
    for cid in query.pending_rejections:
        reject_one(w, cid)
    w["catalog"].update({item["id"]: item for item in items})
    w["candidates"] = items
    w["rag_results"] = guides
    await spot_search.enrich_parents(w, items, local_tool)
    spot_search.publish(w, query, batch, items, location_excluded + excluded)
    return query.summary(len(items), summary)


async def turn_page(w, args, progress, recommend):
    search = w.get("spot_search")
    if not search:
        if args.get("reject_current"):
            for p in list(w["catalog"].values()):
                if p.get("kind") == "spot" and p["id"] not in w["selected_spots"]:
                    reject_one(w, p["id"])
        raise DataError("尚无本轮推荐，请先通过对话筛选景点。")
    current = page_info(w)
    reject = bool(args.get("reject_current"))
    if reject:
        for cid in current["ids"]:
            if cid not in w["selected_spots"]:
                reject_one(w, cid)
    target = int(
        args.get("page") or (current["page"] if reject else current["page"] + 1)
    )
    if target < 1 or target > 50:
        raise DataError("无效的景点页码。")
    pages = max(1, math.ceil(len(groups(w)) / PAGE_SIZE))
    if target > pages:
        raise DataError(
            "当前推荐没有更多页面。可以在对话中让我重新筛选或指定其他景点名称；已选内容保留。"
        )
    search["page"] = target
    w["discovery_mode"] = False
    return (
        f"已显示第{target}页景点。"
        + ("已排除本页未选择的候选。" if reject else "已有选择保留。")
        + "选择完成后点击“完成景点选择”。"
    )


async def search_initial(w, progress, recommend):
    return await search(w, {}, progress, recommend)


def reject_one(w, cid):
    p = w["catalog"].get(cid)
    if not p or p.get("kind") != "spot":
        raise DataError("景点候选已失效。")
    if cid in w["selected_spots"]:
        raise DataError("请先取消选择，再标记为不感兴趣。")
    w["rejected_spots"] = list(dict.fromkeys(w.get("rejected_spots", []) + [cid]))
    w["rejected_spot_names"] = list(
        dict.fromkeys(w.get("rejected_spot_names", []) + [clean_name(p["name"])])
    )
