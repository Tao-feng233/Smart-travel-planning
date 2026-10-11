"""Preload needed road pairs and resolve journey boundaries."""

import asyncio
from app.travel import journey, stay_plan


async def prepare_routes(ctx):
    ctx.progress("通过高德 MCP 比较步行、公交与驾车，检查时间衔接")
    from app.travel.locations import hotel_anchor, quote_stale

    ctx.hotel = ctx.workspace.get("hotel")
    ctx.base = hotel_anchor(ctx.workspace)
    all_pairs = {}
    ctx.warnings = []
    ctx.return_time = None
    if ctx.workspace.get("selected_return"):
        try:
            from datetime import datetime

            ctx.return_time = datetime.fromisoformat(
                ctx.workspace["selected_return"]["departure"].replace(" ", "T")
            )
        except (KeyError, ValueError):
            ctx.warnings.append("所选返程班次的出发时刻需核实。")
    for d in ctx.groups:
        origin = stay_plan.anchor(ctx.workspace, d["date"], morning=True)
        target = stay_plan.anchor(ctx.workspace, d["date"])
        if ctx.return_time and d["date"] == ctx.return_time.date().isoformat():
            target = origin
        seq = (
            ([origin] if origin else [])
            + [ctx.catalog[x["candidate_id"]] for x in d["items"]]
            + ([target] if target else [])
        )
        for a, b in zip(seq, seq[1:]):
            all_pairs[a["id"], b["id"]] = (a, b)
    sem = asyncio.Semaphore(3)

    async def pair(k, ab):
        async with sem:
            return (k, await ctx.services.route_options(*ab))

    ctx.routes = (
        {}
        if ctx.preview
        else dict(await asyncio.gather(*(pair(k, v) for k, v in all_pairs.items())))
    )
    ctx.computed = []
    ctx.boundary_issues = []
    ctx.offered = []
    ctx.meal_unplaced = []
    ctx.scheduled_meals = set()
    if not ctx.base:
        ctx.warnings.append(
            ("已选住宿位置尚未核实" if ctx.hotel else "未确定住宿位置")
            + "，日程尚不包含住宿往返；更新住宿位置后请重新生成。"
        )
    if quote_stale(ctx.hotel):
        ctx.warnings.append(
            "已保留"
            + ctx.hotel["name"]
            + "作为住宿位置；原房型或列表报价已过期，本次住宿实际总价需重新核实。"
        )
    ctx.transport = ctx.workspace.get("selected_transport")
    ctx.arrival = None
    if not ctx.transport and ctx.requirements.get("origin"):
        ctx.warnings.append(
            (
                "自驾或往返自行安排："
                if journey.transport_optional(ctx.requirements)
                else "尚未选择往返班次："
            )
            + "每天开始时间是规划假设；请确认实际抵达与离开时间，首尾日保留调整空间。"
        )
    if ctx.transport:
        try:
            from datetime import datetime

            ctx.arrival = datetime.fromisoformat(
                ctx.transport["arrival"].replace(" ", "T")
            )
        except (KeyError, ValueError):
            ctx.warnings.append("所选交通的到达时间格式需核实。")
