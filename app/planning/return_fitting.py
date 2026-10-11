"""Fit flexible return-day visits using the actual meal and road scheduler."""

from copy import copy, deepcopy

from app.core.errors import DataError
from app.travel import foods


def fixed(schedule, item):
    request = schedule.ctx.workspace.get("visit_requests", {}).get(
        item["candidate_id"], {}
    )
    return item.get("fixed_duration") or request.get("duration") is not None


def trial(schedule, duration):
    """Isolate event/issue writes; share only facts and the per-plan road cache."""
    shadow = copy(schedule)
    shadow.ctx = copy(schedule.ctx)
    for name in ("warnings", "boundary_issues", "offered", "meal_unplaced", "computed"):
        setattr(shadow.ctx, name, list(getattr(schedule.ctx, name)))
    shadow.ctx.scheduled_meals = set(schedule.ctx.scheduled_meals)
    shadow.events = deepcopy(schedule.events)
    shadow.inside_periods = set(schedule.inside_periods)
    shadow.group = deepcopy(schedule.group)
    shadow.item = shadow.group["items"][schedule.index]
    shadow.duration = duration
    for item in shadow.group["items"][schedule.index + 1 :]:
        if not fixed(schedule, item):
            item["duration"] = min(item["duration"], 30)
    return shadow


async def fits(schedule, duration, *, allow_closed=False):
    shadow = trial(schedule, duration)
    try:
        if await shadow.complete_visit() != "placed":
            return False
        await shadow.visits(schedule.index + 1, fit=False)
        await shadow.after_lunch()
        await shadow.dinner()
        await shadow.hotel_transfer()
    except DataError as error:
        context = error.context or {}
        if context.get("phase") == "route":
            raise
        if (
            context.get("code") == "visit_window"
            and context.get("available_minutes") == 0
            and context.get("candidate_ids") == [schedule.point["id"]]
        ):
            raise
        return False
    expected = {
        item["candidate_id"] for item in schedule.group["items"][schedule.index :]
    }
    placed = {e["candidate_id"] for e in shadow.events if e["kind"] == "spot"}
    skipped_closed = (
        {
            candidate_id
            for issue in shadow.ctx.boundary_issues
            if issue.get("code") == "opening_hours"
            and issue.get("available_minutes", 0) < 15
            for candidate_id in issue.get("candidate_ids", [])
        }
        if allow_closed
        else set()
    )
    if not expected <= placed | skipped_closed or shadow.time > shadow.latest_end():
        return False
    # A trial that quietly omitted a selected meal is not a usable schedule.
    for period in ("lunch", "dinner"):
        if foods.choice(schedule.ctx.workspace, schedule.group["date"], period):
            if schedule.group["date"] + "|" + period not in shadow.ctx.scheduled_meals:
                return False
    return True


async def fit(schedule):
    if not schedule.is_return_day():
        return
    original = schedule.duration
    if await fits(schedule, original):
        return
    context = {
        "phase": "return_day",
        "date": schedule.group["date"],
        "view": "spot",
        "candidate_ids": [schedule.point["id"]],
    }
    if fixed(schedule, schedule.item):
        if await fits(schedule, original, allow_closed=True):
            return
        raise DataError(
            "返程前无法容纳"
            + schedule.point["name"]
            + "的固定游玩时长，请调整其他活动或返程班次。",
            {**context, "code": "fixed_duration"},
        )
    minimum = min(original, 30)
    # Meal placement changes at window boundaries, so feasibility is not monotonic.
    # Descend in five-minute planning units rather than using binary search.
    candidates = list(range((original - 1) // 5 * 5, minimum, -5)) + [minimum]
    # First try to keep every visit. If a closed place cannot be retained at any
    # duration, preserve the existing explicit opening-hours skip behavior.
    for duration, allow_closed in [(d, False) for d in candidates] + [
        (d, True) for d in [original] + candidates
    ]:
        if await fits(schedule, duration, allow_closed=allow_closed):
            schedule.duration = duration
            if duration == original:
                return
            schedule.ctx.boundary_issues.append(
                {
                    **context,
                    "code": "return_day_trim",
                    "level": "info",
                    "original_minutes": original,
                    "adjusted_minutes": duration,
                    "message": schedule.point["name"]
                    + "已按返程前可用时间调整为"
                    + str(duration)
                    + "分钟的局部游览，保留后续景点、用餐与通行。",
                }
            )
            return
    raise DataError(
        schedule.point["name"] + "在返程前剩余时间不足以合理游览；"
        "道路、餐次与准备时间已保留，请减少当天安排或改乘更晚班次。",
        {
            **context,
            "code": "return_day_capacity",
            "available_minutes": max(0, schedule.latest_end() - schedule.time),
            "needed_minutes": minimum,
        },
    )
