"""Assemble the book and assess selected lodging, cost and fixed requirements."""

from datetime import date, timedelta
from app.core.errors import DataError
from app.travel import foods, journey, stay_plan
from app.travel.locations import quote_stale
from app.travel.spot_hierarchy import notes
from app.planning import pacing, visit_analysis, transport_links
from app.planning.time_values import minute, clock


def initialize(ctx):
    plan = {
        "title": ctx.draft.get("title") or ctx.requirements["city"] + "旅行计划",
        "summary": "",
        "days": ctx.computed,
        "created": ctx.services.now(),
        "packing": ctx.draft.get("packing", []),
        "todos": ctx.draft.get("todos", []),
        "guides": ctx.guides,
        "warnings": ctx.warnings,
        "stale": False,
        "usage": ctx.usage,
    }
    plan["parent_coverage"] = ctx.hierarchy["parent_coverage"]
    plan["warnings"] += notes(ctx.workspace)
    plan["transfer_links"] = (transport_links.current(ctx.workspace) or {}).get(
        "links", {}
    )
    if (
        ctx.return_time
        and ctx.return_time.hour * 60 + ctx.return_time.minute
        < transport_links.offset(ctx.workspace, "return")
    ):
        plan["warnings"].append(
            "返程接驳与候车准备需要提前到返程日期之前开始；请确认前一晚的退房、夜间交通及具体出发时刻，不能假设返程当日才准备即可。"
        )
    plan["planning_issues"] = ctx.draft.get("planning_issues", [])
    plan["planning_issues"] += ctx.boundary_issues
    plan["planning_issues"] += ctx.offered
    plan["meal_unplaced"] = ctx.meal_unplaced
    for d in ctx.computed:
        group = next((g for g in ctx.groups if g["date"] == d["date"]))
        limit = minute(ctx.requirements.get("day_end", "18:30"))
        if any((i.get("period") == "evening" for i in group["items"])):
            limit = max(limit, 22 * 60)
        finish = max(
            [
                minute(e["end"])
                for e in d["events"]
                if e.get("kind")
                not in ("transport", "arrival", "transfer_plan", "free")
                and (not e.get("route_scope"))
            ]
            + [0]
        )
        if finish > limit:
            plan["planning_issues"].append(
                {
                    "code": "revision_day_end",
                    "level": "warning",
                    "view": "spot",
                    "date": d["date"],
                    "candidate_ids": [i["candidate_id"] for i in group["items"]],
                    "overrun_minutes": finish - limit,
                    "available_minutes": max(
                        0, limit - minute(ctx.requirements.get("day_start", "09:00"))
                    ),
                    "message": d["date"]
                    + "按当前游览建议和路线计算，活动约在"
                    + clock(finish)
                    + "结束，超过每日结束时间"
                    + clock(limit)
                    + "。可调整安排，也可继续生成并保留这一提醒；结束时间设置未被自动修改。",
                }
            )
    plan["selection_notices"] = visit_analysis.notices(
        ctx.workspace,
        [{**item, "date": d["date"]} for d in ctx.groups for item in d["items"]],
    )

    return plan


def add_notices(ctx, plan):
    for key, value in ctx.workspace.get("meal_choices", {}).items():
        if value.get("mode") == "chosen" and key not in ctx.scheduled_meals:
            meal_date, meal_period = key.split("|")
            food_name = (
                ctx.workspace.get("catalog", {}).get(value.get("food_id")) or {}
            ).get("name")
            plan["warnings"].append(
                meal_date
                + " "
                + foods.PERIODS.get(meal_period, "用餐")
                + "的餐厅选择"
                + (f"（{food_name}）" if food_name else "")
                + "未能放入当前日程，请结合抵达和返程时间调整。"
            )
    plan["warnings"] += (
        ctx.services.validate_plan(plan, ctx.requirements)
        + journey.selection_assessment(ctx.workspace)["messages"]
    )
    if ctx.transport:
        plan["todos"].insert(
            0,
            "请注意核实去程"
            + ctx.transport.get("name", "班次")
            + "与返程"
            + (ctx.workspace.get("selected_return") or {}).get("name", "班次")
            + "的最终时刻、车站或机场及席别。",
        )
    plan["packing"].insert(
        0, "请携带并妥善保管身份证件、手机和支付工具；出发前检查证件是否有效。"
    )
    plan["warnings"] += [
        "景点出游日期的开放/预约窗口与当前拥挤程度尚未全面核实。",
        "游玩、用餐、休息和缓冲时长为建议值；地图路线为查询时预计值。",
        "往返交通、酒店入住条件与住宿费用未全部确认时，本计划为待完善草稿；具体房型可选，不影响按住宿位置规划。",
    ]


def lodging_budget(ctx, plan):
    if (
        ctx.hotel
        and ctx.hotel.get("price") is not None
        and (not quote_stale(ctx.hotel))
    ):
        nights = max(
            0,
            (
                date.fromisoformat(
                    (ctx.hotel.get("query_conditions") or {}).get("checkOut")
                    or (ctx.start + timedelta(days=ctx.days)).isoformat()
                )
                - ctx.start
            ).days,
        )
        rooms = int(ctx.requirements.get("rooms") or 1)
        plan["budget"] = {
            "hotel_reference": float(ctx.hotel["price"]) * nights * rooms,
            "nights": nights,
            "rooms": rooms,
            "basis": "列表起价 × 晚数 × 房间数，仅参考，不是已确认住宿总价",
            "unknown": [
                "往返交通",
                "门票实际日期及适用票种",
                "餐饮",
                "市内交通",
                "额外项目",
            ],
        }
    else:
        plan["budget"] = {
            "hotel_reference": None,
            "unknown": ["住宿", "往返交通", "门票", "餐饮", "市内交通"],
        }
    plan["nightly_stays"] = stay_plan.assignment_map(ctx.workspace)
    if "stay_hotels" in ctx.workspace:
        refs = []
        unknown = []
        rooms = int(ctx.requirements.get("rooms") or 1)
        for night, cid in plan["nightly_stays"].items():
            h = ctx.catalog.get(cid) or {}
            q = h.get("query_conditions") or {}
            try:
                value = (
                    float(h["price"])
                    if not quote_stale(h)
                    and q.get("checkIn", "9999") <= night < q.get("checkOut", "0000")
                    else None
                )
            except (KeyError, TypeError, ValueError):
                value = None
            if value is None:
                unknown.append(night + "住宿价格")
            refs.append(
                {
                    "date": night,
                    "hotel_id": cid,
                    "reference": value * rooms if value is not None else None,
                }
            )
        priced = [x for x in refs if x["reference"] is not None]
        plan["budget"] = {
            "hotel_reference": sum((x["reference"] for x in priced))
            if priced
            else None,
            "nights_priced": len(priced),
            "nights": len(refs),
            "rooms": rooms,
            "basis": "各晚有效列表起价参考分别汇总（仅计入已给出价格的 "
            + str(len(priced))
            + " 晚），非已确认房费；未知项未按零计算",
            "nightly_reference": refs,
            "unknown": unknown
            + [
                "往返交通",
                "门票实际日期及适用票种",
                "餐饮",
                "市内交通",
                "房型与实际住宿总价",
            ],
        }


def check_requirements(ctx, plan):
    rest_issues = pacing.required_rest_issues(ctx.workspace, ctx.computed)
    if rest_issues:
        raise DataError(
            rest_issues[0]["message"],
            {"phase": "schedule", "issues": rest_issues, "view": "spot"},
        )
    ctx.services.fill_budget(plan, ctx.workspace)
    plan["selected_room"] = ctx.workspace.get("selected_room")
    if ctx.hotel and (not ctx.workspace.get("selected_room")):
        plan["budget"]["unknown"].append("具体房型及住宿实际总价（可选，预订前核实）")
    plan["meal_choices"] = ctx.workspace.get("meal_choices", {})
    checkout = (ctx.hotel or {}).get("query_conditions", {}).get("checkOut")
    checkin = (ctx.hotel or {}).get("query_conditions", {}).get("checkIn")
    if (
        ctx.hotel
        and checkin
        and ctx.arrival
        and (ctx.arrival.date().isoformat() < checkin)
    ):
        plan["warnings"].append(
            "所选班次于"
            + ctx.arrival.date().isoformat()
            + "抵达，"
            + ctx.hotel["name"]
            + "的原住宿查询从"
            + checkin
            + "开始；可先前往该酒店，但提前抵达当晚入住、加住及费用需确认，不假设已安排。"
        )
    if (
        checkout
        and ctx.return_time
        and (checkout != ctx.return_time.date().isoformat())
    ):
        plan["warnings"].append(
            "住宿报价截至"
            + checkout
            + "，返程为"
            + ctx.return_time.date().isoformat()
            + "；请确认是否需要延住、提前退房或寄存行李，当前房型报价未覆盖日期变化。"
        )
    if ctx.workspace.get("selected_room"):
        plan["warnings"].extend(
            ctx.workspace["selected_room"].get("review", {}).get("issues", [])
        )
        plan["budget"]["selected_room_quote"] = ctx.workspace["selected_room"].get(
            "price"
        )
        plan["budget"]["basis"] = (
            plan["budget"].get("basis", "住宿费用尚未确认")
            + "；已选房型报价单独展示，报价覆盖的日期与总额需核实"
        )
    for key in ("selected_transport", "selected_return"):
        if (ctx.workspace.get(key) or {}).get("selection_status") == "recommended":
            plan["warnings"].append("推荐交通班次尚待用户确认。")
    budget_limit = ctx.requirements.get("budget")
    if (
        budget_limit
        and plan["budget"]["hotel_reference"] is not None
        and (plan["budget"]["hotel_reference"] > float(budget_limit))
    ):
        plan["warnings"].append(
            "仅住宿起价参考已超出总预算，需重新选择；其他费用尚未计入。"
        )


def assemble(ctx):
    plan = initialize(ctx)
    add_notices(ctx, plan)
    lodging_budget(ctx, plan)
    check_requirements(ctx, plan)
    return plan
