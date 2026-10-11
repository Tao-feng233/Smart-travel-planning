"""Context action implementations."""

from app.core.errors import DataError
from app.travel.requirements import update_requirements, mark_stale


async def do_chat(w, action, args, progress, services):
    return ""


async def do_requirements(w, action, args, progress, services):
    r = w["requirements"]
    update_requirements(w, args.get("patch", {}))
    if (
        w.get("spots_confirmed")
        and w.get("stage") == "住宿"
        and all(r.get(k) for k in ("start_date", "days", "adults"))
    ):
        return await services.handle(w, "search_hotels", {}, progress)
    return "旅行信息已保存。请在右侧继续当前步骤。"


async def do_weather(w, action, args, progress, services):
    p = next(
        (
            w["catalog"][i]
            for i in w["selected_spots"]
            if w["catalog"][i].get("location")
        ),
        None,
    )
    if not p:
        raise DataError("先查询或选择一个目的地景点，用真实坐标查天气。")
    progress("查询和风预报及当前官方预警")
    w["weather"] = await services.local_tool(
        "daily_weather", {"location": p["location"]}
    )
    mark_stale(w)
    return "天气已更新。仅覆盖返回的预报日期；当前预警不能当作未来出游日的预警。"
