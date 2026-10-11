"""Assistant action implementations."""

from app.application import guidance


async def do_request_auto_selection(w, action, args, progress, services):
    from app.agents.auto_selection import request

    w["ui"] = guidance.describe(
        w,
        action,
        view="food" if args.get("auto_categories") == ["food"] else "spot",
        status="loading",
    )
    return request(w, args)


async def do_arrange_remaining(w, action, args, progress, services):
    from app.agents.auto_selection import arrange

    return await arrange(w, args, progress, services.llm, services.handle)


async def do_undo(w, action, args, progress, services):
    from app.agents.edit_tools import perform

    return await perform(w, "undo", {}, services.handle, progress)


async def do_approve_auto_selection(w, action, args, progress, services):
    from app.agents.auto_selection import run

    result = await run(
        w,
        args,
        progress,
        services.llm,
        services.handle,
        continuing=action == "continue_auto_selection",
    )
    if w.get("assistant_goal", {}).get("mode") == "delegate":
        w["assistant_goal"]["status"] = (
            "running"
            if w.get("auto_selection_run")
            else "awaiting_confirmation"
            if w.get("pending_plan_warning")
            else "partial"
            if w.get("auto_selection_result", {}).get("errors")
            else "completed"
        )
    w["ui"] = guidance.describe(
        w,
        action,
        view="plan" if w.get("plan") and not w["plan"].get("stale") else "food",
        status="loading",
    )
    return result


async def do_cancel_auto_selection(w, action, args, progress, services):
    from app.agents.auto_selection import cancel

    return cancel(w)
