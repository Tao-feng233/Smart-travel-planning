"""Lodging action implementations."""

from app.core.errors import DataError
from app.travel.requirements import mark_stale
from app.application import guidance
from app.travel import journey
from app.travel.choices import select_room, transport_select


async def do_select_room(w, action, args, progress, services):
    answer = select_room(w, args.get("room_id") or args.get("id"))
    mark_stale(w)
    return answer


async def do_complete_hotel(w, action, args, progress, services):
    r = w["requirements"]
    from app.travel.locations import selected_hotel

    if action == "complete_hotel" and "stay_hotels" in w:
        from app.travel.stay_plan import unassigned

        left = unassigned(w)
        if left:
            raise DataError(
                "还有 "
                + str(len(left))
                + " 晚没有选住宿（"
                + "、".join(left)
                + "）。请逐晚指定，或选择暂不安排住宿。"
            )
    if action == "complete_hotel" and "stay_hotels" in w:
        from app.travel.stay_plan import assignment_map

        invalid = [
            day
            for day, cid in assignment_map(w).items()
            if not selected_hotel(
                {
                    **w,
                    "hotel": w.get("catalog", {}).get(cid)
                    or (
                        w.get("hotel")
                        if (w.get("hotel") or {}).get("id") == cid
                        else None
                    ),
                }
            )
        ]
        if invalid:
            raise DataError("这些夜晚的住宿位置需要重新核对：" + "、".join(invalid))
    if action == "complete_hotel" and not selected_hotel(w):
        raise DataError("请选择有效住宿，或点击“暂不安排住宿”。")
    if action == "skip_hotel":
        w["stay_skipped"] = True
        w["hotel"] = None
        w["selected_room"] = None
        for key in ("stay_hotels", "stay_plan", "selected_rooms"):
            w.pop(key, None)
        mark_stale(w)
    w["stage"] = "交通"
    if journey.is_local(r) or journey.transport_optional(r):
        w["ui"] = guidance.describe(w, "complete_hotel", view="food", status="loading")
        return "往返交通可自行安排，无需选择车票或机票。可以查看餐饮安排；出发与抵达时刻尚未明确时，首尾日保持弹性。"
    missing = [
        label
        for key, label in [
            ("origin", "出发城市"),
            ("start_date", "出发日期"),
            ("days", "旅行天数"),
        ]
        if not r.get(key)
    ]
    if missing:
        return (
            "住宿步骤已确认。请补充**" + "、".join(missing) + "**，随后推荐往返交通。"
        )
    errors = []
    # 往返交通改为用户填写（见《往返交通改为用户填写-设计文档》）。
    # 本项目无法完成真正的订票，因此【不再自动代选班次】——
    # 系统替用户挑一趟车，既没有真正订票，也不该替用户决定行程。
    # 这里只检查用户该填的信息是否齐全，不写 selected_transport。
    for direction, slot, keys in [
        ("outbound", "selected_transport",
         ("outbound_date", "arrival_period", "arrival_station", "arrival_time")),
        ("return", "selected_return",
         ("return_period", "return_station", "return_time")),
    ]:
        if w.get(slot):
            continue
        if not any(r.get(k) for k in keys):
            label = "返程" if direction == "return" else "去程"
            errors.append("未填" + label + "站点与时间")
    w["ui"] = guidance.describe(w, action, view="transport", status="loading")
    if not errors:
        return "往返交通已按你填写的信息记录。" + journey.next_step(w)["message"]
    return (
        "往返交通由你自行安排：请在「旅行信息」里填**到达站与到达时间**、"
        "**返程站与返程时间**。班次信息仍可查询作参考，但不再作为可选项。"
        + ("\n待补充：" + "、".join(errors) + "。")
    )


async def do_hotel_detail(w, action, args, progress, services):
    r = w["requirements"]
    p = w["catalog"].get(args.get("id"))
    if not p or p["kind"] != "hotel":
        raise DataError("请选择已查询的酒店")
    if p.get("stale"):
        raise DataError("酒店条件已变化，请重新查询")
    if not r.get("start_date"):
        raise DataError("请先明确入住日期")
    await services.load_hotel_detail(w, p, progress)
    return "房型详情已更新。请核对日期、人数、餐食与退改；列表起价仍不是确认后的总价。"


async def do_search_hotels(w, action, args, progress, services):
    r = w["requirements"]
    if not r.get("start_date") or not r.get("adults"):
        raise DataError("查住宿前，请补充出游日期和成人/儿童人数。")
    return await services.search_hotels(w, args, progress, services.recommend)
