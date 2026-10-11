"""Suggested midday rest and leisure buffers shared by preview and planning."""

import math

REST_LIMITS = {"rest_minutes": (60, 30, 120), "break_minutes": (30, 15, 60)}
MEAL_TIME_WINDOWS = {
    "breakfast_time": (450, 570),
    "lunch_time": (660, 840),
    "dinner_time": (990, 1200),
}
MEAL_LENGTHS = {
    "breakfast_minutes": (40, 30, 60),
    "lunch_minutes": (75, 45, 90),
    "dinner_minutes": (60, 45, 90),
}


def contract():
    """The same limits used to validate model pacing suggestions."""
    return {
        **{
            key: {"default": default, "minimum": low, "maximum": high}
            for key, (default, low, high) in {**REST_LIMITS, **MEAL_LENGTHS}.items()
        },
        **{
            key: {"format": "HH:MM", "minimum_minute": low, "maximum_minute": high}
            for key, (low, high) in MEAL_TIME_WINDOWS.items()
        },
    }


def required_rest_issues(w, days):
    """Explicit rest is a user constraint; suggested rest remains flexible."""
    from app.planning import schedule
    from app.travel import visits
    from app.planning.diagnostics import issue

    requested = w["requirements"].get("midday_rest_minutes")
    if (
        not isinstance(requested, (int, float))
        or requested <= 0
        or w["requirements"].get("cancel_rest")
    ):
        return []
    result = []
    for dt in visits.dates(w):
        events = next((d.get("events", []) for d in days if d["date"] == dt), [])
        low, high = schedule.windows(w, dt)
        rests = [
            e
            for e in events
            if e.get("rest_type") == "midday"
            and schedule.minutes(e.get("start"), -1) >= low
            and schedule.minutes(e.get("end"), 1441) <= high
        ]
        arranged = sum(
            max(0, schedule.minutes(e.get("end")) - schedule.minutes(e.get("start")))
            for e in rests
        )
        if arranged < requested:
            result.append(
                issue(
                    "fixed_rest",
                    dt
                    + "要求午休"
                    + str(requested)
                    + "分钟，当前只安排了"
                    + str(arranged)
                    + "分钟。需要移动灵活活动或调整可用时间；没有自动取消你的休息要求。",
                    dt=dt,
                    ids=[e["candidate_id"] for e in events if e.get("kind") == "spot"],
                    view="spot",
                )
            )
    return result


def normalize(row):
    out = {}
    for key, (default, low, high) in REST_LIMITS.items():
        value = row.get(key, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ValueError("午休或机动时间建议超出有效范围")
        out[key] = math.ceil(value / 15) * 15
    import re

    for key, (low, high) in MEAL_TIME_WINDOWS.items():
        value = row.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value
        ):
            raise ValueError("餐次时间格式无效")
        h, m = map(int, value.split(":"))
        at = h * 60 + m
        if not low <= at <= high:
            raise ValueError("建议餐次时间超出可调整窗口")
        out[key] = value
    for key, (default, low, high) in MEAL_LENGTHS.items():
        value = row.get(key, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ValueError("用餐时长无效")
        out[key] = value
    out["reason"] = str(
        row.get("reason") or "为午餐后休息、拍照和临时停留保留宽裕时间。"
    )[:240]
    return out


def for_day(w, dt):
    from app.planning.visit_analysis import current

    rows = w.get("_pacing_override")
    if rows is None:
        rows = (current(w) or {}).get("day_pacing", [])
    row = next((x for x in rows if x.get("date") == dt), {})
    policy = normalize(row)
    explicit = w["requirements"].get("midday_rest_minutes")
    if explicit is not None:
        policy["rest_minutes"] = explicit
    policy["basis"] = "model_estimate" if row else "initial_estimate"
    return policy


def rest_length(w, dt, start):
    from app.planning.schedule import windows

    # Do not manufacture a nap on a late arrival or beyond a train deadline.
    if start >= 16 * 60:
        return 0
    high = windows(w, dt)[1]
    return max(0, min(for_day(w, dt)["rest_minutes"], high - start, 1440 - start))


def reserved(w, dt, low, high):
    from app.planning.schedule import meal_start, PERIODS

    lunch = meal_start(w, dt, "lunch")
    if lunch is None:
        return 0
    start = lunch + meal_duration(w, dt, "lunch")
    return max(0, min(high, start + rest_length(w, dt, start)) - max(low, start))


def meal_time(w, dt, period):
    # 早餐固定 08:00 开始（用户口径：不推断起床/睡眠）；午餐 12:00、晚餐 17:00 为默认值。
    defaults = {"breakfast": 480, "lunch": 720, "dinner": 1020}
    value = for_day(w, dt).get(period + "_time")
    if not value:
        return defaults[period]
    h, m = map(int, value.split(":"))
    return h * 60 + m


def meal_duration(w, dt, period):
    return for_day(w, dt)[period + "_minutes"]
