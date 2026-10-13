"""Validate requirement changes and invalidate only dependent snapshots."""

import re
from datetime import date, timedelta

from app.travel import journey
from app.core.errors import DataError


def mark_stale(w):
    if w.get("plan"):
        w["plan"]["stale"] = True


PREFERENCE_FIELDS = ("preferences", "food_preferences")


def validate_query_date(value):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise DataError("日期格式应为 YYYY-MM-DD") from None
    if parsed < date.today():
        raise DataError("请使用今天或之后的查询日期")
    return parsed.isoformat()


def preference_changes(old, updates):
    """Compute list operations before changing any workspace state."""
    if not isinstance(updates, dict) or set(updates) - set(PREFERENCE_FIELDS):
        raise DataError("偏好修改只支持旅行偏好与餐饮偏好。")
    result = {}
    for field, operation in updates.items():
        if not isinstance(operation, dict) or set(operation) - {"mode", "values"}:
            raise DataError("请提供偏好操作方式和内容。")
        mode = operation.get("mode")
        values = operation.get("values")
        if (
            mode not in ("add", "replace", "remove")
            or not isinstance(values, list)
            or any(not isinstance(v, str) for v in values)
        ):
            raise DataError("偏好操作支持追加、替换或移除，内容必须是文字列表。")
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        current = list(old.get(field) or [])
        result[field] = (
            list(dict.fromkeys(current + values))
            if mode == "add"
            else values
            if mode == "replace"
            else [v for v in current if v not in values]
        )[-20:]
    return result


def invalidate_transport_queries(w, direction, expected_date=None):
    """Keep matching dated query snapshots; invalidate only obsolete candidates."""

    def obsolete(record):
        query_date = (record.get("query_conditions") or {}).get("departureDate") or str(
            record.get("departure") or ""
        )[:10]
        return expected_date is None or query_date != expected_date

    for key, record in list(w.get("transport_queries", {}).items()):
        if key.endswith(":" + direction) and obsolete(record):
            w["transport_queries"].pop(key)
    for candidate in w.get("catalog", {}).values():
        candidate_direction = (
            "return" if candidate.get("direction") == "return" else "outbound"
        )
        if (
            candidate.get("kind") in ("train", "flight")
            and candidate_direction == direction
            and obsolete(candidate)
        ):
            candidate["stale"] = True
    current = w.get("transport")
    if (
        current
        and ("return" if current.get("direction") == "return" else "outbound")
        == direction
        and obsolete(current)
    ):
        w["transport"] = None


def update_requirements(w, patch, *, preference_updates=None):
    allowed = {
        "city",
        "origin",
        "start_date",
        "days",
        "adults",
        "children",
        "child_ages",
        "companion_notes",
        "midday_rest_minutes",
        "rooms",
        "budget",
        "pace",
        "transport_mode",
        "preferences",
        "food_preferences",
        "hard_constraints",
        "day_start",
        "day_end",
        "return_date",
        "outbound_date",
        "end_date",
        "local_trip",
        "intercity_mode",
        # 往返交通改为用户填写（见《往返交通改为用户填写-设计文档》3.1）
        "origin_station",
        "arrival_station",
        "arrival_time",
        "arrival_period",
        "return_station",
        "return_arrival_station",
        "return_time",
        "return_period",
        "intercity_ticket_cost",
    }
    clean = {k: v for k, v in patch.items() if k in allowed and v is not None}
    if "city" in clean:
        if not isinstance(clean["city"], str) or not 1 <= len(clean["city"].strip()) <= 80:
            raise DataError("请提供有效的目的地名称。")
        clean["city"] = clean["city"].strip()
    if clean.get("end_date") and (
        clean.get("start_date") or w["requirements"].get("start_date")
    ):
        clean["days"] = (
            date.fromisoformat(clean["end_date"])
            - date.fromisoformat(
                clean.get("start_date") or w["requirements"]["start_date"]
            )
        ).days + 1
    for k, low, high in [
        ("days", 1, 60),
        ("adults", 1, 10),
        ("children", 0, 6),
        ("rooms", 1, 5),
        ("midday_rest_minutes", 0, 120),
    ]:
        if k in clean:
            clean[k] = int(clean[k])
            if not low <= clean[k] <= high:
                raise DataError(f"{k} 超出第一版支持范围 {low}—{high}")
    for field in ("start_date", "return_date", "outbound_date"):
        if field not in clean:
            continue
        try:
            dt = date.fromisoformat(clean[field])
        except ValueError:
            raise DataError("日期格式应为 YYYY-MM-DD") from None
        if dt < date.today():
            raise DataError("请使用今天或之后的出游日期")
    if (
        "budget" in clean
        and clean["budget"] is not None
        and float(clean["budget"]) <= 0
    ):
        raise DataError("预算需大于0")
    for k in ("day_start", "day_end"):
        if k in clean and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clean[k]):
            raise DataError("每日时间应为 HH:MM")
    if "pace" in clean and clean["pace"] not in ("relaxed", "balanced", "packed"):
        raise DataError("不支持的行程节奏")
    if "transport_mode" in clean and clean["transport_mode"] not in (
        "balanced",
        "walking",
        "transit",
        "driving",
    ):
        raise DataError("不支持的交通偏好")
    if (
        clean.get("intercity_mode") == "self_drive"
        and clean.get("transport_mode", "balanced") == "balanced"
    ):
        clean["transport_mode"] = "driving"
    if "intercity_mode" in clean and clean["intercity_mode"] not in (
        "tickets",
        "self_drive",
        "self_arranged",
    ):
        raise DataError("不支持的往返交通安排")
    # 往返时段：只接受三个明确取值；精确时刻由 travel_time 校验 HH:MM 形式。
    for key in ("arrival_period", "return_period"):
        if key in clean and clean[key] not in (None, "", "morning", "afternoon", "evening"):
            raise DataError("时段只能是上午、下午或晚上")
    old = w["requirements"]
    for key in (
        "preferences",
        "food_preferences",
        "hard_constraints",
        "companion_notes",
    ):
        if key in clean:
            clean[key] = list(dict.fromkeys([*old.get(key, []), *clean[key]]))[-20:]
    if preference_updates is not None:
        edited = preference_changes(old, preference_updates)
        if set(patch) & set(edited):
            raise DataError("同一偏好不能同时追加条件和指定编辑操作。")
        clean.update(edited)
    combined = {**old, **clean}
    if (
        combined.get("return_date")
        and combined.get("start_date")
        and combined["return_date"] < combined["start_date"]
    ):
        raise DataError("返程日期不能早于出游日期。")
    defaults = {"children": 0, "child_ages": [], "rooms": 1}
    changed = {
        k
        for k, v in clean.items()
        if (defaults[k] if k in defaults and old.get(k) is None else old.get(k)) != v
    }
    transport_dates_changed = set()
    for key, slot, direction in [
        ("outbound_date", "selected_transport", "outbound"),
        ("return_date", "selected_return", "return"),
    ]:
        effective = str((w.get(slot) or {}).get("departure") or "")[
            :10
        ] or journey.travel_date(old, direction)
        if key in changed and clean[key] != effective:
            transport_dates_changed.add(key)
        if slot in w and not w[slot]:
            w[slot] = None
    if "city" in changed and old.get("city"):
        w.update(
            candidates=[],
            catalog={},
            selected_spots=[],
            hotel=None,
            weather=None,
            transport=None,
            selected_transport=None,
            selected_return=None,
            tickets={},
        )
        for key in (
            "spot_search",
            "web_guides",
            "spot_page",
            "destinations",
            "rejected_spots",
            "rejected_spot_names",
            "selected_room",
            "hotel_query",
            "transport_queries",
            "meal_choices",
            "food_query",
            "visit_requests",
            "dining_reviewed",
            "stay_hotels",
            "stay_plan",
            "center_hotel_quotes",
            "selected_rooms",
            "travel_timing",
            "timeline_review",
            "travel_preview",
            "transport_links",
        ):
            w.pop(key, None)
    if "city" in changed:
        w["spots_confirmed"] = False
    if {"start_date", "days", "adults", "children", "child_ages", "rooms"} & changed:
        if w.get("hotel"):
            w["hotel"].update(stale=True, quote_stale=True)
        w["selected_room"] = None
        w.pop("selected_rooms", None)
        w.pop("hotel_query", None)
        if {"start_date", "days", "adults", "children", "child_ages"} & changed:
            w["tickets"] = {}
        # Retain factual snapshots but mark candidates from old query conditions unusable.
        for p in w.get("catalog", {}).values():
            if p.get("kind") == "hotel":
                p["stale"] = True
    if "return_date" in transport_dates_changed:
        w["selected_return"] = None
        invalidate_transport_queries(w, "return", clean["return_date"])
    if "outbound_date" in transport_dates_changed:
        w["selected_transport"] = None
        invalidate_transport_queries(w, "outbound", clean["outbound_date"])
    if "origin" in changed:
        w["transport"] = None
        w["selected_transport"] = None
        w["selected_return"] = None
        w.pop("transport_queries", None)
        invalidate_transport_queries(w, "outbound")
        invalidate_transport_queries(w, "return")
    if "intercity_mode" in changed and clean["intercity_mode"] != "tickets":
        w["selected_transport"] = None
        w["selected_return"] = None
        w.pop("transport_links", None)
    if changed:
        mark_stale(w)
    w["requirements"].update(clean)
    if "midday_rest_minutes" in clean:
        w["requirements"].pop("cancel_rest", None)
    if (
        {"days", "start_date"} & changed
        and "end_date" not in clean
        and w["requirements"].get("start_date")
        and w["requirements"].get("days")
    ):
        w["requirements"]["end_date"] = (
            date.fromisoformat(w["requirements"]["start_date"])
            + timedelta(days=w["requirements"]["days"] - 1)
        ).isoformat()
    if {"start_date", "days"} & changed:
        valid = journey.meal_dates(w["requirements"])
        w["meal_choices"] = {
            k: v
            for k, v in w.get("meal_choices", {}).items()
            if k.split("|")[0] in valid
        }
    # 往返交通由用户填写（不再选班次）。合成必须放在上面那些"
    # 日期/出发地变化就清空 selected_transport/selected_return"的逻辑【之后】，
    # 否则刚合成好的记录又会被清掉。
    # 只有用户确实填了时刻相关信息时才合成，避免无谓改写已有记录。
    if {"arrival_time", "arrival_period", "return_time", "return_period",
            "arrival_station", "return_station", "outbound_date",
            "return_date", "start_date", "days"} & changed:
        from app.travel import travel_synthesis

        travel_synthesis.apply(w)
