"""Validated itinerary inputs and proposal acquisition."""

from app import prompts
import json
from datetime import date, timedelta
from app.core.errors import DataError
from app.integrations.contracts import guide_conditions
from app.planning.proposals import create


async def prepare(ctx):
    from app.travel.spot_hierarchy import state, parent_facts

    ctx.hierarchy = state(ctx.workspace)
    if ctx.hierarchy["issues"]:
        raise DataError(
            ctx.hierarchy["issues"][0]["message"],
            {"issues": ctx.hierarchy["issues"], "view": "spot"},
        )
    ctx.workspace = {
        **ctx.workspace,
        "visit_requests": ctx.hierarchy["visit_requests"],
        "visit_order": ctx.hierarchy["visit_order"],
    }
    ctx.requirements = ctx.workspace["requirements"]
    ctx.catalog = ctx.workspace.get("catalog", {})
    from app.planning import transport_links

    await transport_links.resolve(
        ctx.workspace,
        ctx.progress,
        ctx.services.tool,
        ctx.services.route_options,
        ctx.services.choose_route,
    )
    ctx.spots = [ctx.catalog[i] for i in ctx.hierarchy["active_ids"]]
    if not ctx.spots:
        raise DataError("请先选择想去的景点")
    if not ctx.requirements.get("start_date"):
        raise DataError("请先确定出游日期")
    ctx.days = int(ctx.requirements.get("days", 2))
    ctx.start = date.fromisoformat(ctx.requirements["start_date"])
    ctx.guides = (
        ctx.workspace.get("rag_results", [])
        if ctx.preview
        else (
            await ctx.services.tool(
                "retrieve_guides",
                guide_conditions(
                    ctx.requirements["city"],
                    " ".join((x["name"] for x in ctx.spots)) + " 开放 预约",
                    ctx.requirements,
                ),
            )
        )["items"]
    )
    if not ctx.preview:
        ctx.progress("主助手正在组织每天的景点顺序与游览建议")
    schema = '{"title":"旅行主题","days":[{"date":"YYYY-MM-DD","theme":"当日主题","items":[{"candidate_id":"真实候选ID","period":"morning/afternoon/evening/any","duration":90,"note":"游玩建议与日期时段安排理由","evidence_ids":["资料ID"]}]}],"packing":["携带建议"],"todos":["出发前待办"]}'
    ctx.prompt = prompts.system("plan")
    tour_dates = [(ctx.start + timedelta(days=i)).isoformat() for i in range(ctx.days)]
    finish = max(
        tour_dates[-1],
        (ctx.workspace.get("selected_return") or {}).get("departure", "")[:10]
        or ctx.requirements.get("return_date")
        or tour_dates[-1],
    )
    begin = min(
        ctx.start.isoformat(),
        (ctx.workspace.get("selected_transport") or {}).get("departure", "")[:10]
        or ctx.start.isoformat(),
    )
    span = (date.fromisoformat(finish) - date.fromisoformat(begin)).days + 1
    if span > 90:
        raise DataError("完整旅途跨度超过90天，请按阶段分别规划。")
    ctx.payload = {
        "requirements": ctx.requirements,
        "parent_coverage": ctx.hierarchy["parent_coverage"],
        "parent_context": parent_facts(ctx.workspace),
        "dates": [
            (date.fromisoformat(begin) + timedelta(days=i)).isoformat()
            for i in range(span)
        ],
        "tour_dates": tour_dates,
        "spots": ctx.spots,
        "visit_requests": ctx.workspace.get("visit_requests", {}),
        "visit_order": ctx.workspace.get("visit_order", []),
        "selected_room": ctx.workspace.get("selected_room"),
        "hotel": ctx.workspace.get("hotel"),
        "selected_transport": ctx.workspace.get("selected_transport"),
        "selected_return": ctx.workspace.get("selected_return"),
        "official_guides": ctx.guides,
    }
    if ctx.workspace.get("planning_feedback"):
        ctx.payload["validation_feedback"] = (
            ctx.workspace["planning_feedback"]
            + "。调整可变景点日期或同日顺序，保留已选地点、班次、餐厅与用户明确日期时段，不可修改用户选择来掩盖冲突。"
        )
    from app.planning import visit_analysis

    ctx.payload["output_schema"] = json.loads(schema)
    ctx.payload["interaction_state"] = prompts.interaction_state(ctx.workspace)
    ctx.payload["day_budgets"] = visit_analysis.budgets(ctx.workspace)
    ctx.payload["visit_analysis"] = visit_analysis.current(ctx.workspace)
    ctx.payload["initial_balanced_estimate"] = visit_analysis.preview(ctx.workspace)
    from app.agents.recommendation_context import context

    ctx.payload["recommendation_context"] = context(ctx.workspace)
    ctx.payload["meal_choices"] = {
        key: {**value, "food": ctx.catalog.get(value.get("food_id"))}
        for key, value in ctx.workspace.get("meal_choices", {}).items()
    }
    if ctx.workspace.get("planning_revision"):
        ctx.payload["revision_context"] = ctx.workspace["planning_revision"]
    ctx.dates = ctx.payload["dates"]


async def propose(ctx):
    if ctx.preview:
        from app.planning.schedule import provisional, conflicts

        issues = conflicts(ctx.workspace)
        if issues:
            raise DataError(issues[0]["message"], {"issues": issues, "view": "spot"})
        by_date = {}
        for row in provisional(ctx.workspace):
            if row["kind"] != "spot":
                continue
            by_date.setdefault(row["date"], []).append(
                {
                    "candidate_id": row["candidate_id"],
                    "period": row["period"],
                    "duration": row["duration"],
                    "not_before": row.get("not_before"),
                    "sequence": row.get("sequence"),
                    "note": row.get("reason", ""),
                }
            )
        ctx.groups = [{"date": dt, "items": items} for dt, items in by_date.items()]
        ctx.draft = {
            "title": "道路核对后的建议安排",
            "packing": [],
            "todos": [],
            "planning_issues": [],
        }
        ctx.usage = {}
    else:
        ctx.draft, ctx.groups, ctx.usage = await create(
            ctx.workspace,
            ctx.spots,
            ctx.payload,
            ctx.prompt,
            ctx.progress,
            ctx.services.model,
            ctx.services.runtime,
        )
    for dt in ctx.dates:
        if dt not in {d["date"] for d in ctx.groups}:
            ctx.groups.append({"date": dt, "theme": "弹性休息日", "items": []})
    ctx.groups.sort(key=lambda x: x["date"])
