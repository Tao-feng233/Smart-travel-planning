"""Hotel querying owns nightly anchors, factual quote snapshots and room lookup."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from app.core.errors import DataError
from app.integrations import enrichment
from app.integrations.responses import unwrap
from app.persistence.storage import now
from app.travel import access, locations, stay_plan
from app.travel.choices import room_choices
from app.travel.hotel_candidates import add_children, candidate, records
from app.planning import time_policy


@dataclass(frozen=True)
class HotelServices:
    tuniu: Callable
    local_tool: Callable
    route_options: Callable
    choose_route: Callable
    query_budget: Callable


async def prepare_nights(w, args, services):
    chosen = [
        w["catalog"][cid] for cid in w["selected_spots"] if cid in w.get("catalog", {})
    ]
    if not chosen:
        raise DataError(
            "先选择景点，我再按每天最后一个活动的位置推荐住宿。也可以明确告诉我想先查哪个住宿区域。"
        )
    city = (w.get("requirements") or {}).get("city") or ""
    for mode, key in (("arrival", "selected_transport"), ("return", "selected_return")):
        transport = w.get(key)
        if isinstance(transport, dict) and transport.get("departure"):
            await time_policy.resolve_station(
                w, transport, mode, city, services.local_tool
            )
    stay = stay_plan.merge_plan(w, stay_plan.plan(w), w.get("stay_plan"))
    if not stay["nights"]:
        raise DataError("本次行程没有需要住宿的夜晚，可以直接继续规划。")
    w["stay_plan"] = stay
    explicit = args.get("stay_dates") or (
        [args["stay_date"]] if args.get("stay_date") else []
    )
    unknown = [day for day in explicit if day not in stay["nights"]]
    if unknown:
        raise DataError("查询日期不在本次住宿夜晚内：" + "、".join(unknown))
    budget = await services.query_budget()
    if explicit:
        targets = explicit
    elif budget > 0:
        targets = stay["nights"][:budget]
    else:
        raise DataError("当前酒店查询额度不足，请稍后重试；已有住宿选择保留。")
    return stay, explicit, budget, targets


async def query_zone(w, day, row, params, progress, services):
    """在给定查询参数下取一次候选，并做位置与通行核对。返回可用 items。"""
    add_children(params, w["requirements"])
    result = await services.tuniu("hotel", "tuniuHotelSearch", params)
    items = [
        candidate(
            hotel,
            result["source"],
            dict(params),
            day + " 入住列表起价，房型与总价待核实",
            suffix="@" + day,
            quote_fields={
                "quote_date": day,
                "stay_date": day,
                "stay_anchor_id": row.get("anchor_id"),
                "stay_anchor_name": row.get("anchor_name"),
            },
        )
        for hotel in records(result)[:8]
    ]
    if not items:
        return [], [], []
    items, location_excluded = await locations.ready_candidates(
        w, items, services.local_tool, locate_hotels=True
    )
    if not items:
        return [], location_excluded, []
    anchor = (w.get("catalog") or {}).get(row.get("anchor_id"))
    items, excluded = await access.screen(
        w, items, lambda _: anchor, services.route_options, services.choose_route
    )
    return items, location_excluded, excluded


async def query_night(w, day, progress, services):
    """查某一晚的酒店：锚定检索为空时【逐级扩大范围】，直到有可核实候选。

    实测依据（洛阳 2026-10-14，白马寺一带）：
      一级 poiName=白马寺     → 途牛 1 条 → 可核实 0 家
      二级 poiName=景点中心一带 → 途牛 8 条 → 可核实 5 家
      三级 整城（无 poiName）   → 途牛 8 条 → 可核实 5 家
    只做一级时用户得到"暂无可用酒店"，而往外退一级就有 5 家。

    注意：扩大范围只扩大【检索范围】，坐标与通行核对【不允许放宽】——
    没有核实到坐标的酒店仍然不进候选，只是让检索有机会遇到能核实的酒店。
    """
    row = next(row for row in w["stay_plan"]["rows"] if row["date"] == day)
    base_params = stay_plan.day_search_plan(w, day)

    # 第 1 级：当天收尾地点锚定
    progress(
        "以"
        + str(row.get("anchor_name") or w["requirements"]["city"])
        + "为中心（"
        + str(row.get("anchor_basis") or "当天收尾地点")
        + "）查询 "
        + day
        + " 当晚住宿"
    )
    candidates = [(1, dict(base_params))]
    # 第 2 级：改用全部已选景点中心一带检索；第 3 级：整城检索。
    params_center, _nearest, _count = stay_plan.center_search_plan(w)
    if params_center:
        center = dict(params_center)
        center["checkIn"] = day
        center["checkOut"] = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        if center.get("poiName") != base_params.get("poiName"):
            candidates.append((2, center))
    city_only = {k: v for k, v in base_params.items() if k != "poiName"}
    candidates.append((3, city_only))

    attempted, items, location_excluded, excluded = [], [], [], []
    for level, params in candidates[:3]:
        attempted.append(level)
        if level > 1:
            progress(
                "这一晚在"
                + ("景点一带" if level == 2 else "全城范围")
                + "扩大检索"
            )
        try:
            found, loc_ex, ex = await query_zone(
                w, day, row, params, progress, services
            )
        except DataError:
            found, loc_ex, ex = [], [], []
        location_excluded = location_excluded + loc_ex
        excluded = excluded + ex
        if found:
            items = found
            if level > 1:
                progress("核对 " + day + " 候选酒店的位置与到当天收尾地点的通行")
                for item in found:
                    item["anchor_route"] = item["access"].get("route")
                    item["route_options"] = item["access"].get("options", [])
                    item["anchor_name"] = row.get("anchor_name")
                    item["recommendation_basis"] = (
                        "当天收尾地点「"
                        + str(row.get("anchor_name"))
                        + "」附近没有可核实的酒店，已把检索范围扩大到"
                        + ("景点一带" if level == 2 else "全城")
                        + "；以下候选均经位置与通行核对。"
                    )
                    item["dinner_hint"] = stay_plan.dinner_options(w, day, item)
            break

    if items:
        for item in items:
            item.setdefault("anchor_route", item["access"].get("route"))
            item.setdefault("route_options", item["access"].get("options", []))
            item.setdefault("anchor_name", row.get("anchor_name"))
            item.setdefault(
                "recommendation_basis",
                "以当天收尾地点「"
                + str(row.get("anchor_name"))
                + "」为参照（"
                + str(row.get("anchor_basis") or "当天最后一个活动")
                + "），核对 "
                + day
                + " 当晚通行；"
                + ("已核算该路段。" if item.get("anchor_route") else "实际通行尚待核实。"),
            )
            item.setdefault("dinner_hint", stay_plan.dinner_options(w, day, item))
        w["catalog"].update({item["id"]: item for item in items})

    widened = attempted[-1] if items and len(attempted) > 1 else 0
    row.update(
        candidate_ids=[item["id"] for item in items],
        queried_at=now(),
        empty=not items,
        excluded=location_excluded + excluded,
        widen_level=widened,
        widen_tried=attempted,
    )
    return items


async def query_center(w, params, nearest, count, progress, services):
    progress("按全部已选景点的中心（" + str(count) + " 个地点）查询主住宿候选")
    try:
        result = await services.tuniu("hotel", "tuniuHotelSearch", params)
        hotels = records(result)
    except DataError:
        return []
    items = []
    for hotel in hotels[:4]:
        item = candidate(
            hotel,
            result["source"],
            dict(params),
            "全程列表起价，房型与总价待核实",
            suffix="@center",
        )
        item.update(
            anchor_name="全部已选景点的中心",
            anchor_basis="全部已选景点的中心（" + str(count) + " 个地点）",
            center_of_spots=True,
            recommendation_basis=(
                "以全部 "
                + str(count)
                + " 个已选景点的中心为参照，"
                + ("最近参照点为「" + str(nearest["name"]) + "」；" if nearest else "")
                + "适合设为主住宿、其余夜晚沿用。"
            ),
        )
        items.append(item)
    if items:
        items, _ = await locations.ready_candidates(
            w, items, services.local_tool, locate_hotels=True
        )
        w["catalog"].update({item["id"]: item for item in items})
    return items


def publish_nights(w, collected, center_matches, targets, skipped, center_count):
    # Per-night queries replace the visible batch, while the primary hotel bank
    # stays available for a later choice covering several nights.
    bank = {**(w.get("center_hotel_quotes") or {})}
    bank.update({item["id"]: item["id"] for item in center_matches})
    if bank:
        w["center_hotel_quotes"] = bank
    center_ids = [
        cid
        for cid in (w.get("center_hotel_quotes") or {})
        if cid in (w.get("catalog") or {})
    ]
    w["hotel_query"] = {
        **(w.get("hotel_query") or {}),
        "keyword": "",
        "ids": [item["id"] for item in collected],
        "anchor": (stay_plan.row_for(w, targets[0]) or {}).get("anchor_name"),
        "anchor_basis": "逐晚以当天最后一个活动为锚点",
        "center_matches": center_ids,
        "center_basis": "全部已选景点的中心（" + str(center_count) + " 个地点）"
        if center_count
        else "全部已选景点的中心",
        "source": collected[0].get("source") if collected else None,
        "stay_plan": w["stay_plan"],
        "skipped_nights": skipped,
    }
    w["candidates"] = collected
    w["stage"] = "住宿"


async def nightly_summary(w, stay, collected, targets, skipped, recommend):
    if not collected:
        where = "、".join(
            str((stay_plan.row_for(w, day) or {}).get("anchor_name") or "当天收尾地点")
            for day in targets
        )
        return (
            "本次在"
            + where
            + "周边没有查到酒店。这仅是本次查询结果，不能断定附近没有住宿；可换锚点或放宽条件后重查。"
        )
    lines = []
    for row in stay["rows"]:
        names = [
            (w["catalog"].get(cid) or {}).get("name")
            for cid in (row.get("candidate_ids") or [])
        ]
        names = [name for name in names if name]
        onway = [
            item["name"]
            for item in (row.get("dinner_hint") or [])
            if item.get("on_the_way")
        ]
        lines.append(
            "· "
            + row["date"]
            + " 住"
            + str(row.get("anchor_name") or "待定")
            + "周边（"
            + str(row.get("anchor_basis") or "")
            + "）"
            + ("：" + "、".join(names) if names else "：本次未查，可点“查这晚”")
        )
        if onway:
            lines[-1] += "；晚餐顺路建议：" + "、".join(onway)
    tail = (
        "\n受每日查询额度限制，以下晚次尚未查询，可点对应晚次单独查："
        + "、".join(skipped)
        if skipped
        else ""
    )
    summary = await recommend(
        w,
        collected,
        "按每天收尾地点分别比较位置与通行；每晚给出一组候选，不把未核算路线当最优",
    )
    return (
        "已按行程逐晚安排住宿，每晚以当天最后一个活动为中心：\n"
        + "\n".join(lines)
        + tail
        + "\n"
        + summary
    )


async def search(w, args, progress, recommend, services):
    if args.get("keyword"):
        return await search_keyword(w, args, progress, recommend, services)
    stay, explicit, budget, targets = await prepare_nights(w, args, services)
    skipped = [day for day in stay["nights"] if day not in targets]
    collected = []
    for day in targets:
        collected += await query_night(w, day, progress, services)
    w["stay_plan"]["assignments"] = stay_plan.assignment_view(w)
    params, nearest, count = stay_plan.center_search_plan(w)
    center_matches = []
    if params and not explicit and len(targets) < budget:
        center_matches = await query_center(
            w, params, nearest, count, progress, services
        )
    publish_nights(w, collected, center_matches, targets, skipped, count)
    return await nightly_summary(w, stay, collected, targets, skipped, recommend)


async def search_keyword(w, args, progress, recommend, services):
    r = w["requirements"]
    keyword = args.get("keyword") or ""
    progress("按关键词“" + str(keyword) + "”查询途牛酒店候选")
    params = {
        "cityName": r.get("city"),
        "checkIn": r.get("start_date"),
        "checkOut": (
            date.fromisoformat(r["start_date"])
            + timedelta(days=max(1, int(r.get("days", 2))))
        ).isoformat(),
        "adultNum": int(r.get("adults") or 2),
        "keyword": keyword,
    }
    add_children(params, r)
    result = await services.tuniu("hotel", "tuniuHotelSearch", params)
    hotels = records(result)
    w["hotel_query"] = {
        **(w.get("hotel_query") or {}),
        "keyword": keyword,
        "ids": [],
        "anchor": r.get("city"),
        "anchor_basis": "按关键词直接查询，未按当天收尾地点锚定",
        "source": result["source"],
    }
    if not hotels:
        w["candidates"] = []
        return (
            "本次未查到“"
            + str(keyword)
            + "”相关酒店（"
            + str(r.get("start_date"))
            + " 入住）。"
            "这仅是本次查询结果，不能断定该品牌在当地没有门店；您对位置、价格或房型有什么偏好？"
            "可据此换关键词，也可以改用按每天收尾地点的住宿推荐。"
        )
    items = [
        candidate(hotel, result["source"], params, "指定日期列表起价，房型与总价待核实")
        for hotel in hotels[:4]
    ]
    progress("核对候选酒店的地图位置与地址")
    items, excluded = await locations.ready_candidates(
        w, items, services.local_tool, locate_hotels=True
    )
    w["hotel_query"].update(excluded=excluded, ids=[item["id"] for item in items])
    w["candidates"] = items
    w["catalog"].update({item["id"]: item for item in items})
    w["stage"] = "住宿"
    if not items:
        return "本次酒店候选尚未核对到有效坐标，暂不列入推荐。可更换关键词或稍后重试地图查询；已选住宿保留。"
    summary = await recommend(
        w,
        items,
        "按用户指定关键词查询；未按当天收尾地点比较，位置是否合适请结合行程判断",
    )
    return summary + "\n可展开房型信息。选定酒店后再生成包含住宿往返的计划书。"


async def load_detail(w, p, progress, services):
    r = w["requirements"]
    quote = p.get("query_conditions") or {}
    checkin = quote.get("checkIn") or r.get("start_date")
    if not checkin:
        raise DataError("请先明确入住日期")
    checkout = (
        quote.get("checkOut")
        or (
            date.fromisoformat(checkin) + timedelta(days=max(1, int(r.get("days", 2))))
        ).isoformat()
    )
    progress(
        "途牛 MCP 正在查询酒店房型与退改信息"
        + (("（" + str(p.get("stay_date")) + " 入住）") if p.get("stay_date") else "")
    )
    params = {
        "hotelId": int(p["provider_id"]),
        "checkIn": checkin,
        "checkOut": checkout,
        "adultNum": int(quote.get("adultNum") or r.get("adults", 2)),
        "roomNum": int(quote.get("roomNum") or r.get("rooms", 1)),
    }
    add_children(params, r, detail=True)
    result = await services.tuniu("hotel", "tuniuHotelDetail", params)
    data = unwrap(result["data"])
    p["detail_source"] = result["source"]
    if not isinstance(data, dict):
        raise DataError("酒店详情未返回可用结构，请稍后重试。")
    p["detail"] = enrichment.hotel_detail(
        data,
        {
            **r,
            "start_date": checkin,
            "days": max(
                1, (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
            ),
        },
    )
    p["room_choices"] = room_choices(p, {**r, "start_date": checkin})
    if (
        not p.get("address")
        and isinstance(data.get("address"), str)
        and data["address"]
    ):
        p["address"] = data["address"]
        p["address_source"] = result["source"]
    if not locations.coordinate(p.get("location")) and p.get("name"):
        await locations.locate_hotel(w, p, services.local_tool)
    if isinstance(data.get("firstPic"), str) and data["firstPic"]:
        p["photos"] = list(dict.fromkeys([data["firstPic"]] + p.get("photos", [])))[:8]
    if (w.get("hotel") or {}).get("id") == p["id"]:
        w["hotel"]["detail"] = p["detail"]
        if p.get("address"):
            w["hotel"]["address"] = p["address"]
    return p["detail"].get("availability_status")
