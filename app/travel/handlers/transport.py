"""Transport action implementations."""

import re
from app.core.errors import DataError
from app.travel.requirements import update_requirements, validate_query_date
from app.application import guidance
from app.travel import journey
from app.travel.choices import train_seat
from app.integrations.responses import unwrap


async def do_transport_arrangement(w, action, args, progress, services):
    r = w["requirements"]
    choice = args.get("mode") or r.get("intercity_mode")
    if choice not in ("tickets", "self_drive", "self_arranged"):
        raise DataError("请选择自驾、往返自行安排或查询班次。")
    update_requirements(
        w,
        {
            "intercity_mode": choice,
            **({"transport_mode": "driving"} if choice == "self_drive" else {}),
        },
    )
    w["ui"] = guidance.describe(
        w,
        action,
        view="transport" if choice == "tickets" else "food",
        status="ready",
    )
    return (
        "可按需要查询班次，车票与机票由你自行选定。"
        if choice == "tickets"
        else "已设为"
        + ("自驾游" if choice == "self_drive" else "往返自行安排")
        + "，无需选择车票或机票，可以继续规划。出发与抵达时刻尚未明确时，首尾日保持弹性。"
    )


async def do_train(w, action, args, progress, services):
    r = w["requirements"]
    if journey.is_local(r):
        return (
            "出发地与目的地为同一区域，无需查询外地往返班次，可以直接生成市内游玩计划。"
        )
    if not r.get("start_date") or not r.get("origin"):
        raise DataError("请先补充出发城市和出游日期。")
    # Query controls are published before calling the provider.
    params = {
        "departureCityName": r["origin"],
        "arrivalCityName": r["city"],
        "departureDate": journey.travel_date(r, "outbound"),
    }
    direction = "return" if args.get("direction") == "return" else "outbound"
    if direction == "return":
        params = {
            "departureCityName": r["city"],
            "arrivalCityName": r["origin"],
            "departureDate": journey.travel_date(r),
        }
    if args.get("departure_date"):
        params["departureDate"] = validate_query_date(args["departure_date"])
    tool = "searchLowestPriceTrain" if action == "train" else "searchLowestPriceFlight"
    if action == "train":
        params.update(pageSize=30, searchType="3" if args.get("recommend") else "5")
    start = args.get("time_start")
    end = args.get("time_end")
    if start or end:
        if (
            not start
            or not end
            or not all(
                re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in (start, end)
            )
            or start >= end
        ):
            raise DataError("请选择有效的出发时间段，起点必须早于终点。")
        params["departureTime"] = start + "-" + end
        if action == "flight":
            params["searchType"] = "TIME"
    w["query_controls"] = {
        "kind": action,
        "direction": direction,
        "departure_date": params["departureDate"],
        "time_start": start or "",
        "time_end": end or "",
        "train_type": args.get("train_type", "all"),
    }
    w["ui"]["controls"] = w["query_controls"]
    progress("已设置查询条件，正在查询班次")
    result = await services.tuniu(action, tool, params)
    d = unwrap(result["data"])
    rows = d.get("data", []) if isinstance(d, dict) else []
    if action == "flight" and not isinstance(rows, list):
        rows = []
    if not rows and isinstance(d, dict):
        rows = d.get("flights", []) or d.get("flightList", [])
    if not rows:
        w["transport"] = {
            "items": [],
            "kind": action,
            "direction": direction,
            "source": result["source"],
            "query_conditions": params,
        }
        w.setdefault("transport_queries", {})[action + ":" + direction] = w["transport"]
        return "本次未查到符合条件的班次。请调整日期或出发时段，或切换交通类型；已有选择保留。"
    items = []
    for i, x in enumerate(rows[:30]):
        if action == "train":
            p = dict(
                name=x.get("trainNum", "车次"),
                departure=x.get("departureTime"),
                arrival=x.get("arrivalTime"),
                departure_station=x.get("departStationName")
                or x.get("departureStationName"),
                arrival_station=x.get("destStationName") or x.get("arrivalStationName"),
                **train_seat(x),
                price_basis="单人席别参考票价；成人/儿童规则需核实",
            )
            p["train_type"] = "highspeed" if p["name"].startswith("G") else "regular"
            if (
                args.get("train_type") in ("highspeed", "regular")
                and p["train_type"] != args["train_type"]
            ):
                continue
        else:
            p = dict(
                name=x.get("flightNumber", x.get("flightNo", "航班")),
                departure=x.get("departureTime"),
                arrival=x.get("arrivalTime"),
                departure_station=x.get("departureAirport"),
                arrival_station=x.get("arrivalAirport"),
                price=x.get("basePrice"),
                tax=x.get("totalTax"),
                seats=x.get("remainingSeats"),
                seat_label=str(x.get("remainingSeats", "未知")),
                price_basis="基础票价；税费、舱位和适用人群需核对",
            )
        p.update(
            id=f"tuniu:{action}:{direction}:{params['departureDate']}:{p['name']}:{i}",
            kind=action,
            direction=direction,
            source=result["source"],
            query_conditions=params,
        )
        items.append(p)
    w.setdefault("transport_queries", {})[action + ":" + direction] = {
        "items": items,
        "source": result["source"],
        "query_conditions": params,
    }
    w["transport"] = {
        "items": items,
        "kind": action,
        "direction": direction,
        "source": result["source"],
        "query_conditions": params,
    }
    w["candidates"] = items
    w["catalog"].update({p["id"]: p for p in items})
    w["stage"] = "交通"
    return (
        "当前结果中没有符合车次类型的班次，请调整筛选。"
        if not items
        else "班次已查到。"
    ) + "余票是查询时快照，不能保证之后买到；选择班次会影响可用游玩时间。"
