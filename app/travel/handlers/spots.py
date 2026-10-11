"""Spots action implementations."""

from app.core.errors import DataError
from app.persistence.storage import now
from app.travel.requirements import update_requirements
from app.application import guidance
from app.travel import discovery
from app.integrations import enrichment
from app.integrations.responses import unwrap


async def do_discover_destinations(w, action, args, progress, services):
    r = w["requirements"]
    progress("正在比较目的地特色与旅行偏好")
    items = discovery.destinations()
    guides = (
        await services.local_tool(
            "retrieve_guides",
            {
                "city": "",
                "query": " ".join(r.get("preferences", []))
                + " 目的地概览 海滨 历史 自然",
            },
        )
    )["items"]
    summary = await services.recommend(
        w,
        items,
        "推荐多个不同旅行方向，条件匹配优先；来源是背景资料，不估造路费、天气、客流或保证符合预算",
        guides,
    )
    items.sort(key=lambda p: p.get("recommendation_rank", 99))
    w["destinations"] = items
    w["discovery_mode"] = True
    w["stage"] = "目的地"
    return summary + "\n请在目的地卡片比较特色与代表景点，选择城市后查询具体景点。"


async def do_choose_destination(w, action, args, progress, services):
    item = next(
        (d for d in w.get("destinations", []) if d["id"] == args.get("id")), None
    )
    if not item:
        raise DataError("请选择当前展示的目的地。")
    update_requirements(w, {"city": item["name"]})
    w["discovery_mode"] = False
    return f"已将目的地设置为{item['name']}。\n" + await services.handle(
        w, "search_spots", {}, progress
    )


async def do_complete_spots(w, action, args, progress, services):
    r = w["requirements"]
    if not w["selected_spots"]:
        raise DataError("请至少选择一个景点，再完成此步骤。")
    w["spots_confirmed"] = True
    w["discovery_mode"] = False
    w["stage"] = "住宿"
    analysis = ""
    if r.get("start_date") and r.get("days"):
        from app.planning import visit_analysis

        value = await visit_analysis.analyze(w, services.llm, progress)
        analysis = visit_analysis.summary(w, value) + "\n"
    if int(r.get("days") or 0) == 1:
        w["ui"] = guidance.describe(w, action, view="transport", status="loading")
        return (
            analysis
            + f"已确认景点（{len(w['selected_spots'])}个）。\n本次为一日游，如需当晚住宿可以继续查询，也可跳过住宿。可以比较往返交通，或先生成计划草稿。"
        )
    missing = [
        label
        for key, label in [
            ("start_date", "出游日期"),
            ("days", "旅行天数"),
            ("adults", "成人数"),
        ]
        if not r.get(key)
    ]
    if missing:
        w["ui"] = guidance.describe(w, action, view="hotel", status="loading")
        return (
            analysis
            + f"已确认景点（{len(w['selected_spots'])}个）。\n接下来可以比较住宿。请补充一下{'、'.join(missing)}，可以直接在对话中回复，或填写右侧“旅行信息”。"
        )
    result = await services.handle(w, "search_hotels", {}, progress)
    return (
        analysis
        + f"已确认景点（{len(w['selected_spots'])}个）。现在根据所选景点位置比较住宿。\n"
        + result
    )


async def do_dismiss_spot(w, action, args, progress, services):
    discovery.reject_one(w, args.get("id"))
    w["discovery_mode"] = False
    if w.get("spot_search"):
        w["spot_search"]["page"] = min(
            w["spot_search"]["page"], discovery.page_info(w)["pages"]
        )
    return "已标记为不感兴趣，后续推荐会排除此地点。已有景点选择保留。"


async def do_search_spots(w, action, args, progress, services):
    from app.agents.recommendation_context import needs_preferences, ask

    if needs_preferences(w, args):
        return ask(w)
    return await discovery.search(w, args, progress, services.recommend)


async def do_spots_page(w, action, args, progress, services):
    return await discovery.turn_page(w, args, progress, services.recommend)


async def do_ticket(w, action, args, progress, services):
    cid = args.get("id")
    p = (
        w["catalog"].get(cid)
        if cid
        else next((w["catalog"][i] for i in w["selected_spots"]), None)
    )
    if not p or p["kind"] != "spot":
        raise DataError("请先选择要查门票的景点。")
    requested = enrichment.ticket_date(w, p, args)
    progress("途牛 MCP 正在查询门票产品与适用票种")
    try:
        for query_name in enrichment.ticket_names(p):
            result = await services.tuniu(
                "ticket",
                "query_cheapest_tickets",
                {"scenic_name": query_name, "depart_date": requested},
            )
            d = unwrap(result["data"])
            rows = d.get("tickets", []) if isinstance(d, dict) else []
            if not isinstance(rows, list):
                raise DataError("门票接口未返回可用产品列表。")
            if rows:
                break
    except DataError:
        w.setdefault("tickets", {}).setdefault(p["id"], {"items": []}).update(
            status="query_failed", attempted_date=requested, checked_at=now()
        )
        raise
    w["ui"]["focus_id"] = p["id"]
    w.setdefault("tickets", {})[p["id"]] = enrichment.ticket_snapshot(
        rows, requested, result["source"], query_name, p
    )
    return "门票结果已保存。区间起价可能对应其他日期，学生/老人票不能直接用于成人；商品存在不代表已取得入场预约。"
