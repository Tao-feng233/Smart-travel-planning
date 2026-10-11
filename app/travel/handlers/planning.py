"""Planning action implementations."""

from app.application import guidance
from app.travel import visits


async def do_optimize_plan(w, action, args, progress, services):
    from app.planning.plan_revision import optimize

    return await optimize(w, args, progress, services.llm, services.generate)


async def do_approve_plan_warning(w, action, args, progress, services):
    from app.planning.plan_warnings import approve, cancel

    return approve(w, args) if action == "approve_plan_warning" else cancel(w)


async def do_adjust_timeline(w, action, args, progress, services):
    from app.planning.timeline_tools import apply, optimize
    from app.planning.travel_preview import refresh

    if args.get("timeline_changes"):
        result = await apply(w, args["timeline_changes"], progress)
    else:
        await refresh(w, progress)
        result = await optimize(
            w,
            services.llm,
            progress,
            force=True,
            conflict=(w.get("travel_preview") or {}).get("issues"),
        )
    w["ui"] = guidance.describe(
        w, action, view=w.get("ui", {}).get("view") or "spot", status="loading"
    )
    if result["status"] == "applied":
        return (
            "已通过时间轴工具调整景点顺序、建议游玩时间与餐次，页面已更新。"
            + result.get("reason", "")
            + " 已选地点和班次保留。"
            + (
                "部分道路仍需核对，当前时刻为建议。"
                if not result["roads_checked"]
                else ""
            )
        )
    return result.get("reason") or "当前时间轴未改动；已有选择保留。"


async def do_review_timeline(w, action, args, progress, services):
    return "已核对时间轴，具体建议会显示在对话中的时间安排提醒里；已有选择保留。"


async def do_refresh_routes(w, action, args, progress, services):
    from app.planning.travel_preview import refresh, current

    w["ui"] = guidance.describe(
        w, action, view=w.get("ui", {}).get("view") or "spot", status="loading"
    )
    await refresh(w, progress)
    ready = current(w)
    if ready:
        return "已根据已选住宿、景点、餐厅和班次核对交通并更新时间轴；预计通行与缓冲分开展示，正式计划书尚未重新生成。"
    return (w.get("travel_preview") or {}).get(
        "message"
    ) or "可以在选定景点并提供出游日期后核对交通时间；当前可继续比较地点。"


async def do_visit_schedule(w, action, args, progress, services):
    r = w["requirements"]
    result = visits.save(w, args.get("visit_requests", []), args.get("visit_order"))
    if w.get("plan"):
        from app.planning.plan_revision import optimize

        return (
            result
            + "\n"
            + await optimize(
                w,
                {
                    "instruction": w.get("last_question")
                    or "按刚保存的指定日期与顺序修订计划书。"
                },
                progress,
                services.llm,
                services.generate,
            )
        )
    if r.get("start_date") and r.get("days") and w.get("selected_spots"):
        from app.planning import visit_analysis

        value = await visit_analysis.analyze(w, services.llm, progress)
        result += "\n" + visit_analysis.summary(w, value)
    return result


async def do_analyze_visits(w, action, args, progress, services):
    from app.planning import visit_analysis

    value = await visit_analysis.analyze(w, services.llm, progress, force=True)
    w["ui"] = guidance.describe(w, action, view="spot", status="loading")
    return visit_analysis.summary(w, value)


async def do_plan(w, action, args, progress, services):
    from app.travel.locations import coordinate, locate_hotel

    h = w["catalog"].get((w.get("hotel") or {}).get("id"))
    if h and not coordinate((w.get("hotel") or {}).get("location")):
        progress("正在重新核对已选住宿的位置")
        await locate_hotel(w, h, services.local_tool)
    plan = await services.generate(w, progress)
    from app.planning.plan_warnings import request, waiting

    if request(w, plan):
        return waiting()
    w["plan"] = plan
    w["stage"] = "计划书"
    w.pop("last_plan_conflict", None)
    return (
        "旅行计划书已生成，请查看右侧每日安排。"
        + (
            "\n" + "\n".join(w["plan"].get("selection_notices", []))
            if w["plan"].get("selection_notices")
            else ""
        )
        + "\n**如需调整，直接发送消息告诉我**，例如调整某天景点、更换餐厅或放慢节奏；未核实条件仍标为草稿。"
    )
