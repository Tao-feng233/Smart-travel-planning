"""Dining action implementations."""

from app.core.errors import DataError
from app.travel.requirements import mark_stale
from app.application import guidance
from app.travel import foods


async def do_complete_food(w, action, args, progress, services):
    w["dining_reviewed"] = True
    w["ui"] = guidance.describe(w, "complete_food", view="plan", status="loading")
    return "餐饮安排已确认。未选餐厅的餐次保留自行安排。可以生成旅行计划书，查看完整的每日安排。"


async def do_search_foods(w, action, args, progress, services):
    return await foods.search(w, args, progress, services.recommend)


async def do_meal_choice(w, action, args, progress, services):
    cid = args.get("food_id") or args.get("id")
    p = w["catalog"].get(cid)
    if (
        p
        and args.get("meal_mode", "chosen") == "chosen"
        and args.get("meal_date")
        and args.get("meal_period") in foods.PERIODS
    ):
        blocked = foods.infeasible(w, args["meal_date"], args["meal_period"])
        if not blocked:
            from app.travel.access import check

            refs = foods.anchors(w, args)
            p["access"] = await check(
                w,
                p,
                refs[0] if refs else None,
                services.route_options,
                services.choose_route,
                (args["meal_date"], args["meal_period"]),
            )
            if p["access"]["status"] in ("no_route", "time_conflict"):
                raise DataError(
                    p["name"] + "不适合当前餐次：" + p["access"]["message"],
                    {
                        "date": args["meal_date"],
                        "meal_period": args["meal_period"],
                        "candidate_ids": [cid],
                        "view": "food",
                    },
                )
    result = foods.select_meal(w, args)
    mark_stale(w)
    return result
