"""Schedule one meal with its road leg and optional midday rest."""

from app.core.errors import DataError
from app.travel import foods, stay_plan
from app.planning import pacing, route_cache
from app.planning.time_values import round_up, clock


async def schedule(ctx, dt, period, t, last, duration):
    p = foods.choice(ctx.workspace, dt, period)
    events = []
    included = foods.included_meal(ctx.workspace, dt, period)
    if included["included"]:
        h = stay_plan.hotel_for(ctx.workspace, dt, morning=True)
        events.append(
            {
                "kind": "meal",
                "name": "早餐 · 酒店含早（" + included["note"] + "）",
                "start": clock(t),
                "end": clock(t + duration),
                "meal_period": period,
                "included_in_room": True,
                "candidate_id": h["id"],
                "source": h.get("source"),
                "cost": "房型报价所含权益，适用日期与人数已核对；未预订",
                "note": "按已选房型记录在酒店用餐；如改选外部餐厅，以用户选择为准。",
            }
        )
        ctx.scheduled_meals.add(dt + "|" + period)
        return (events, t + duration, h)
    if p:
        from app.planning.schedule import meal_window, windows

        earliest, latest = meal_window(ctx.workspace, dt, period)
        t = max(t, earliest)
    if p and last:
        options = await route_cache.options(ctx, last, p)
        chosen = ctx.services.choose_route(options, ctx.requirements)
        if not chosen:
            reason = (
                "各方式均未返回方案"
                if options and all((x.get("status") == "no_route" for x in options))
                else "坐标或路线接口尚未核实"
            )
            raise DataError(
                "从"
                + last["name"]
                + "到"
                + p["name"]
                + "的通行未能核实（"
                + reason
                + "），请更新位置或重试查询，也可调整本餐安排。",
                {
                    "date": dt,
                    "meal_period": period,
                    "candidate_ids": [last["id"], p["id"]],
                    "view": "food",
                    "route_options": options,
                    "phase": "route",
                },
            )
        allocation = round_up(chosen["minutes"] + 15)
        events.append(
            {
                "kind": "route",
                "name": "从" + last["name"] + "前往" + p["name"],
                "start": clock(t),
                "end": clock(t + allocation),
                "route": chosen,
                "options": [chosen],
                "buffer": allocation - chosen["minutes"],
                "note": "前往已选用餐地点，含规划缓冲。",
            }
        )
        t += allocation
    elif p and (not last):
        h = ctx.workspace.get("hotel")
        name = h.get("name", "已选酒店") if h else None
        message = (
            name + "的位置尚未取得可用于当前旅行的坐标。"
            if h
            else "当前还没有确定住宿或当天出发位置。"
        )
        message += (
            dt
            + " "
            + foods.PERIODS[period]
            + "已选"
            + p["name"]
            + "，但尚不能计算前往该店的路线。"
        )
        message += (
            "请查看住宿并更新位置"
            + ("。" if h else "，也可确认本餐的实际出发地点。")
            + "已选餐厅和班次保留。"
        )
        raise DataError(
            message,
            {
                "date": dt,
                "meal_period": period,
                "candidate_ids": ([h["id"]] if h else []) + [p["id"]],
                "view": "hotel",
                "phase": "route",
            },
        )
    if p and t + duration > latest and (t + duration > windows(ctx.workspace, dt)[1]):
        raise DataError(
            dt
            + " "
            + foods.PERIODS[period]
            + "（"
            + p["name"]
            + "）含通行后的用餐时间超出当前可用时段，请调整顺序、餐厅或班次后重排。",
            {
                "date": dt,
                "meal_period": period,
                "candidate_ids": [p["id"]],
                "view": "food",
                "direction": "return"
                if ctx.return_time and dt >= ctx.return_time.date().isoformat()
                else "outbound",
            },
        )
    if p and t + duration > latest:
        ctx.warnings.append(
            dt
            + " "
            + foods.PERIODS[period]
            + "预计结束于"
            + clock(t + duration)
            + "，超过默认餐次或每日建议窗口；可调整安排，也可确认后保留这一提醒。"
        )
    name = foods.PERIODS[period] + " · " + (p["name"] if p else "自行安排")
    events.append(
        {
            "kind": "meal",
            "name": name,
            "start": clock(t),
            "end": clock(t + duration),
            "note": "餐厅为规划意向，营业时段、菜单和价格请出发前确认，可随时更换。"
            if p
            else "弹性用餐建议，可自行选择餐厅或调整时间；未预订，费用未核实。",
            **({"food": p, "source": p.get("source")} if p else {}),
        }
    )
    ctx.scheduled_meals.add(dt + "|" + period)
    finish = t + duration
    if period == "lunch":
        rest = pacing.rest_length(ctx.workspace, dt, finish)
        if rest:
            events.append(
                {
                    "kind": "rest",
                    "rest_type": "midday",
                    "name": "午休与放松",
                    "start": clock(finish),
                    "end": clock(finish + rest),
                    "note": pacing.for_day(ctx.workspace, dt)["reason"]
                    + " 就近休息，不默认返回酒店；具体休息条件可按现场情况调整。",
                    "estimated": True,
                }
            )
            finish += rest
        if rest < pacing.for_day(ctx.workspace, dt)["rest_minutes"]:
            ctx.warnings.append(
                dt
                + "午餐后可安排的午休为"
                + str(rest)
                + "分钟，受抵达或返程时间限制；如需更充分休息，可调整该日活动或班次。"
            )
    return (events, finish, p or last)
