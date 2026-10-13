"""Places action implementations."""

from app.core.errors import DataError
from app.persistence.storage import now
from app.travel.requirements import mark_stale
from app.travel import foods
from app.travel.choices import transport_select


async def do_place_detail(w, action, args, progress, services):
    p = w["catalog"].get(args.get("id"))
    if p and p.get("kind") == "hotel":
        from app.travel.locations import locate_hotel

        await locate_hotel(w, p, services.local_tool)
        return p["match_status"]
    if (
        not p
        or not p["id"].startswith("amap:")
        or p.get("kind") not in ("spot", "food", "market")
    ):
        raise DataError("请打开已查询的高德地点详情。")
    try:
        result = await services.local_tool("get_place_details", {"ids": [p["id"]]})
    except DataError:
        p["place_detail_status"] = "query_failed"
        p["place_detail_checked_at"] = now()
        raise
    detail = next((x for x in result.get("items", []) if x.get("id") == p["id"]), None)
    p["place_detail_status"] = "available" if detail else "not_found"
    p["place_detail_checked_at"] = now()
    if detail:
        for k in (
            "address",
            "location",
            "entrance",
            "exit",
            "citycode",
            "city",
            "district",
            "rating",
            "parent_id",
            "children",
            "typecode",
            "poi_type",
            "cost",
            "telephone",
            "alias",
            "business_area",
            "tags",
            "opening",
            "opening_today",
            "opening_week",
            "opening_scope",
            "photos",
        ):
            if detail.get(k) not in (None, "", []):
                p[k] = detail[k]
        p["place_detail_source"] = detail.get("source")
    return (
        "地点详情已更新；来源未提供的字段仍标为待核实。"
        if detail
        else "未查到进一步详情，已保留原有地点资料。"
    )


async def do_select(w, action, args, progress, services):
    cid = args.get("id")
    p = w["catalog"].get(cid)
    if not p:
        raise DataError("候选不存在或已失效，请重新查询")
    if p.get("stale"):
        raise DataError("候选日期或人数条件已经变化，请重新查询后选择")
    answer_extra = ""
    detail_error = ""
    if p["kind"] == "spot":
        from app.travel.spot_choices import choose

        removed, children = choose(w, cid, add_only=args.get("add_only", False))
    elif p["kind"] == "food":
        return foods.select_meal(w, {**args, "food_id": cid})
    elif p["kind"] == "hotel":
        from app.travel import stay_plan

        # 住宿只按晚指定：不再有"主住宿覆盖其余夜晚"。没选的夜晚就是还没选，
        # 界面上如实显示"尚未选这一晚的住宿"，由用户逐晚决定。
        nights = stay_plan.nights(w)
        if not nights:
            raise DataError("当前没有住宿夜晚，请明确需要入住的日期。")
        stay_dates = args.get("stay_dates") or (
            [args["stay_date"]] if args.get("stay_date") else []
        )
        if not stay_dates and p.get("stay_date"):
            stay_dates = [p["stay_date"]]
        if not stay_dates:
            # 未指定夜晚：优先落到最早还没选的晚；全部已选时按"替换第一晚"处理，
            # 而不是报错——调用方（如自动补齐）表达的是"换成这家"，
            # 但逐晚语义下不能因此覆盖其它夜晚。
            left = stay_plan.unassigned(w)
            stay_dates = [left[0] if left else nights[0]]
        assigned = stay_plan.assign(w, p["id"], stay_dates)
        if (w.get("hotel") or {}).get("id") != p["id"]:
            w["selected_room"] = None
        # w['hotel'] 记录"最近选定的这一家"，供房型/计划书锚点等读取；
        # 它不再代表"其余夜晚都住这里"——那些夜晚由 stay_hotels 逐晚决定。
        w["hotel"] = dict(p)
        answer_extra = (
            "已把 " + ("、".join(assigned)) + " 的住宿设为 " + p["name"] + "。"
        )
        w["stay_hotels"] = w.get("stay_hotels") or {}
        w["stay_skipped"] = False
    elif p["kind"] in ("train", "flight"):
        transport_select(w, p, args.get("replace", False))
        # 选定班次后自动审查：提前抵达日要吃住、返程过早则剔除当天住宿。
        # 只说清结论与依据，不在这些天写死时刻。
        from app.planning import travel_review

        review_notices, review_dropped = travel_review.apply(w)
        answer_extra = (
            "\n" + "\n".join("· " + x for x in review_notices) if review_notices else ""
        )
    mark_stale(w)
    if p["kind"] == "spot":
        answer = f"{'已取消选择' if removed else '已选择'}：{p['name']}。当前已选{len(w['selected_spots'])}个景点。\n可继续比较候选，或点击“完成景点选择”进入下一步。"
        if children:
            names = "、".join(w["catalog"][child]["name"] for child in children)
            answer = (
                f"{'已取消' if removed else '已选择'}{p['name']}内部的{len(children)}个游玩地点：{names}。"
                "父景区不再单独计时，内部地点优先连续安排在同一天；实际交通与开放条件核对后再细化。"
                f"当前已选{len(w['selected_spots'])}个景点。"
            )
    elif p["kind"] == "hotel":
        from app.travel import stay_plan as _stay

        rooms = len(p.get("room_choices") or [])
        left = _stay.unassigned(w)
        if rooms:
            answer = (
                answer_extra
                + f"已选择住宿：{p['name']}，房型已展开（{str(rooms)} 个报价）；选定住宿位置即可继续，具体房型可选。"
            )
        elif detail_error:
            answer = (
                answer_extra
                + f"已选择住宿：{p['name']}。房型与报价这次没有取到：{detail_error}可点该卡的“房型详情”重试。"
            )
        else:
            answer = (
                answer_extra
                + f"已选择住宿：{p['name']}。可直接点击“完成住宿选择”继续；具体房型可选，也可稍后再定。选定仅用于规划，尚未预订。"
            )
        if left:
            answer += (
                "\n还有 "
                + str(len(left))
                + " 晚没有选住宿（"
                + "、".join(left)
                + "）：在住宿编排里逐晚挑，没选就是还没选。"
            )
        answer += "\n入住时间尚未因选定酒店而确定。你打算自行安排，还是希望我结合抵达和游玩行程给出建议？"
    else:
        answer = (
            f"已选择{'返程' if p.get('direction') == 'return' else '去程'}班次：{p['name']}。可继续确认另一方向班次，或生成计划草稿。班次尚未预订。"
            + answer_extra
        )
    if w.get("plan"):
        answer += "\n已有计划受选择变更影响，需要重新生成。"
    return answer
