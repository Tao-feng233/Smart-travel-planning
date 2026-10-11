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
    for direction, slot in [
        ("outbound", "selected_transport"),
        ("return", "selected_return"),
    ]:
        if w.get(slot):
            continue
        try:
            await services.handle(
                w, "train", {"direction": direction, "recommend": True}, progress
            )
            candidates = [
                p
                for p in w["transport"]["items"]
                if str(p.get("seats")) != "0"
                and (
                    direction == "return"
                    or (p.get("arrival") or "")[:10] <= journey.travel_date(r)
                )
            ]
            candidates.sort(
                key=lambda p: (
                    0 if p.get("train_type") == "highspeed" else 1,
                    p.get("departure", ""),
                )
            )
            if candidates:
                transport_select(w, candidates[0], recommended=True)
            else:
                errors.append(
                    "未找到符合日期的"
                    + ("返程" if direction == "return" else "去程")
                    + "列车"
                )
        except DataError as e:
            errors.append(str(e))
    w["ui"] = guidance.describe(w, action, view="transport", status="loading")
    if (w.get("selected_transport") or {}).get("selection_status") == "confirmed" and (
        w.get("selected_return") or {}
    ).get("selection_status") == "confirmed":
        return "已保留您确认的往返班次。" + journey.next_step(w)["message"]
    return (
        "已整理推荐往返交通，请在右侧核对时间，可改为其他车次或飞机。推荐尚待确认。"
        if w.get("selected_transport") or w.get("selected_return")
        else "本次尚未取得可推荐班次。请在右侧调整时段或切换飞机继续查询。"
    ) + ("\n" + "；".join(errors) if errors else "")


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
