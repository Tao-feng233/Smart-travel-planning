from app.planning.time_values import (
    minute as minute,
    round_up as round_up,
    clock as clock,
)
import json
from app.core.errors import DataError
from app.integrations.providers import llm
from app.integrations.tools import local_tool
from app.persistence.storage import now, RUNTIME


def parse_review(raw):
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("issues"), list):
        raise ValueError("审核结构无效")
    if any(not isinstance(x, str) for x in value["issues"]):
        raise ValueError("审核问题类型无效")
    if value.get("summary") is not None and not isinstance(value["summary"], str):
        raise ValueError("审核摘要类型无效")
    return {
        "issues": value["issues"][:6],
        "summary": value.get("summary")
        or (
            "审核助手列出了待确认问题，请逐项核实后再出发。"
            if value["issues"]
            else "审核助手未列出额外问题；草稿中已有的待确认事项仍需核实。"
        ),
    }


def validate_plan(plan, requirements):
    issues = []
    for day in plan["days"]:
        previous = -1
        for e in day["events"]:
            start, end = minute(e["start"]), minute(e["end"])
            if start < previous:
                issues.append(f"{day['date']} 的 {e['name']} 与前项时间重叠")
            if end <= start:
                issues.append(f"{e['name']} 时长无效")
            previous = end
        tour_end = max(
            [
                minute(e["end"])
                for e in day["events"]
                if e.get("kind") not in ("transport", "arrival", "transfer_plan")
                and not e.get("route_scope")
            ]
            + [0]
        )
        if tour_end > minute(requirements.get("day_end", "18:30")):
            issues.append(f"{day['date']} 超出每日结束时间，建议减少景点或调整顺序")
    if requirements.get("hard_constraints"):
        issues.append(
            "用户的特殊条件已交给模型审核，尚未全部转成程序约束："
            + "；".join(requirements["hard_constraints"])
        )
    return issues


async def route_options(a, b):
    from app.travel.locations import endpoint

    origin = endpoint(a)
    dest = endpoint(b)
    if not origin or not dest:
        return [
            {
                "mode": m,
                "available": False,
                "status": "missing_location",
                "reason": "起点或终点缺少有效地图坐标",
            }
            for m in ("walking", "transit", "driving")
        ]
    if origin == dest:
        return [
            {
                "mode": "walking",
                "available": True,
                "status": "same_location",
                "minutes": 0,
                "distance": 0,
                "polylines": [],
                "note": "起终点为同一地图坐标，未额外计算道路通行；景区内部移动仍需核实",
            }
        ]

    async def query(x, y):
        options = []
        # Sequential modes bound per-pair bursts; the provider also limits QPS.
        for mode in ("walking", "transit", "driving"):
            if mode == "transit" and not (a.get("citycode") and b.get("citycode")):
                options.append(
                    {
                        "mode": mode,
                        "available": False,
                        "status": "missing_city",
                        "reason": "缺少地图城市代码，公交待核实",
                    }
                )
                continue
            params = {"origin": x, "destination": y, "mode": mode}
            if mode == "transit":
                params.update(
                    citycode=a["citycode"], destination_citycode=b["citycode"]
                )
            try:
                options.append(await local_tool("calculate_route", params))
            except DataError:
                options.append(
                    {
                        "mode": mode,
                        "available": False,
                        "status": "query_failed",
                        "reason": "路线接口查询失败或连接超时，可重试",
                    }
                )
        return options

    options = await query(origin, dest)
    pois = (endpoint(a, False), endpoint(b, False))
    if (
        not any(x.get("available") for x in options)
        and all(pois)
        and pois != (origin, dest)
        and any(x.get("status") == "no_route" for x in options)
    ):
        fallback = await query(*pois)
        if any(x.get("available") for x in fallback):
            for x in fallback:
                if x.get("available"):
                    x["endpoint_fallback"] = True
                    x["note"] = (
                        "入口位置未返回方案，使用地图地点坐标核算；到具体入口的衔接仍需核实。"
                    )
            return fallback
        # An entrance failure cannot override an inconclusive POI retry.
        return fallback
    return options


def choose_route(options, requirements):
    valid = [x for x in options if x.get("available")]
    if not valid:
        return None
    preferred = requirements.get("transport_mode", "balanced")
    if preferred in ("walking", "transit", "driving"):
        return next((x for x in valid if x["mode"] == preferred), None) or min(
            valid, key=lambda x: x["minutes"]
        )
    relaxed = requirements.get("pace") == "relaxed"
    walk = next((x for x in valid if x["mode"] == "walking"), None)
    if walk and walk["minutes"] <= (15 if relaxed else 25):
        return walk
    transit = next((x for x in valid if x["mode"] == "transit"), None)
    driving = next((x for x in valid if x["mode"] == "driving"), None)
    if relaxed and driving:
        return driving
    if transit and transit["minutes"] <= 60:
        return transit
    return driving or min(valid, key=lambda x: x["minutes"])


async def generate(w, progress):
    try:
        return await _generate(w, progress)
    except DataError as e:
        context = e.context or {}
        ids = context.get("candidate_ids", [])
        if context.get("phase") == "schedule":
            from app.planning.timeline_tools import optimize

            repaired = await optimize(
                w, llm, progress, conflict={"message": str(e), "context": context}
            )
            if repaired.get("status") == "applied":
                return await _generate(w, progress)
            raise
        # One bounded repair after querying actual travel times. Hard dates
        # and periods remain intact; a second failure is actionable feedback.
        if (
            context.get("phase") in ("proposal", "route")
            or not ids
            or not any(not w.get("visit_requests", {}).get(cid) for cid in ids)
        ):
            raise
        progress("时间衔接未通过，正在保留已选班次与明确安排、调整可变顺序后重新核对")
        return await _generate({**w, "planning_feedback": str(e)}, progress)


def fill_budget(plan, w):
    """把已有数据能算出的费用如实汇总进 plan['budget']，算不出的才列为待核实。"""
    r = w.get("requirements") or {}
    adults = int(r.get("adults") or 1)
    rooms = int(r.get("rooms") or 1)
    cat = w.get("catalog") or {}
    budget = plan.setdefault("budget", {})
    items = {}

    # 往返交通：单人席别参考票价 × 成人数
    inter = []
    for label, key in (("去程", "selected_transport"), ("返程", "selected_return")):
        t = w.get(key) or {}
        try:
            price = float(t.get("price"))
        except (TypeError, ValueError):
            price = None
        if price is not None:
            inter.append(
                {
                    "label": label + " " + str(t.get("name") or ""),
                    "seat": t.get("seat_type"),
                    "unit": price,
                    "adults": adults,
                    "amount": price * adults,
                    "basis": "单人席别参考票价；成人/儿童规则需核实",
                }
            )
    if inter:
        items["往返交通"] = {"amount": sum(x["amount"] for x in inter), "detail": inter}

    # 市内交通：计划内已核实票价的公交/地铁
    fares = []
    for d in plan.get("days", []):
        for e in d.get("events", []):
            route = e.get("route") or {}
            try:
                fare = float(route.get("fare"))
            except (TypeError, ValueError):
                fare = None
            if fare is not None:
                fares.append(
                    {
                        "date": d["date"],
                        "name": str(e.get("name"))[:40],
                        "fare": fare,
                        "mode": route.get("mode"),
                    }
                )
    if fares:
        items["市内交通"] = {
            "amount": sum(x["fare"] for x in fares),
            "detail": fares,
            "basis": "仅计入已核实票价的公交/地铁；打车与自驾未计入",
        }

    # 餐饮：已选餐厅的参考人均 × 成人数 × 人数餐次
    meals = []
    for key, choice in (w.get("meal_choices") or {}).items():
        if (choice or {}).get("mode") != "chosen":
            continue
        food = cat.get((choice or {}).get("food_id")) or {}
        try:
            cost = float(food.get("cost"))
        except (TypeError, ValueError):
            cost = None
        if cost is None:
            continue
        dt, _, period = key.partition("|")
        meals.append(
            {
                "key": key,
                "name": str(food.get("name") or "")[:30],
                "per_person": cost,
                "adults": adults,
                "amount": cost * adults,
            }
        )
    if meals:
        items["餐饮"] = {
            "amount": sum(x["amount"] for x in meals),
            "detail": meals,
            "basis": "已选餐厅的地图参考人均 × 成人数；非实际消费，未选餐次不计",
        }

    budget["items"] = items
    known = sum(v["amount"] for v in items.values())
    if budget.get("hotel_reference") is not None:
        known += budget["hotel_reference"]
    budget["known_subtotal"] = known
    # 待核实项：只保留真的没有数据的
    pending = []
    if "往返交通" not in items:
        pending.append("往返交通（尚未选定或未取到票价）")
    pending.append("门票实际日期及适用票种（平台未提供票价资料）")
    if "餐饮" not in items:
        pending.append("餐饮（尚未选定餐厅或未取到参考人均）")
    if budget.get("hotel_reference") is None:
        pending.append("住宿")
    if "市内交通" not in items:
        pending.append("市内交通（尚未取到票价）")
    pending.append("打车/自驾油费与停车费")
    if not w.get("selected_room"):
        pending.append("具体房型与实际住宿总价（可选，预订前核实）")
    budget["unknown"] = pending
    budget["basis"] = (
        str(budget.get("basis") or "").rstrip("；")
        + "；已按现有资料汇总可确认部分（"
        + str(round(known))
        + " 元），未取得资料的项仍列为待核实，不按零计入"
    )
    return budget


async def _generate(w, progress, *, preview=False):
    from app.planning.plan_context import PlanContext, PlanningServices
    from app.planning import plan_inputs, plan_routes, plan_output, plan_review
    from app.planning.daily_schedule import DailySchedule

    services = PlanningServices(
        llm,
        local_tool,
        route_options,
        choose_route,
        fill_budget,
        validate_plan,
        parse_review,
        now,
        RUNTIME,
    )
    ctx = PlanContext(w, progress, preview, services)
    await plan_inputs.prepare(ctx)
    await plan_inputs.propose(ctx)
    await plan_routes.prepare_routes(ctx)
    for group in ctx.groups:
        await DailySchedule(ctx, group).build()
    plan = plan_output.assemble(ctx)
    if preview:
        plan["preview"] = True
        plan["review"] = {
            "status": "not_run",
            "summary": "时间轴预览，尚未生成或审核正式计划书。",
        }
    else:
        await plan_review.review(ctx, plan)
    return plan
