"""Public response channel: generated answer only, never raw model reasoning."""

from app import prompts
from contextvars import ContextVar
import json
import re
from app.integrations.providers import llm_stream
from app.integrations.enrichment import model_facts

SINK = ContextVar("reply_sink", default=None)
PREFIX = ContextVar("reply_prefix", default="")


def emit(text):
    sink = SINK.get()
    if sink:
        sink(text)


def acknowledge(text):
    if text and SINK.get():
        text = text.rstrip() + "\n\n"
        PREFIX.set(text)
        emit(text)


def without_repeated_prefix(text, prefix):
    """Ignore whitespace differences when a model echoes the already displayed acknowledgement."""
    target = re.sub(r"\s+", "", prefix)
    if not target:
        return text
    n = 0
    for i, char in enumerate(text):
        if char.isspace():
            continue
        if n >= len(target) or char != target[n]:
            return text
        n += 1
        if n == len(target):
            return text[i + 1 :].lstrip()
    return text


async def compose(w, result):
    from app.planning import visit_analysis

    r = w["requirements"]
    action = w.get("ui", {}).get("action") or w.get("last_action", "chat")
    ids = (w.get("spot_page") or {}).get("ids")
    from app.travel.discovery import page_info

    if w.get("spot_search"):
        ids = page_info(w)["ids"]
    focus = w.get("turn_action") or action
    spots = (
        [w["catalog"][i] for i in ids or [] if i in w["catalog"]]
        if focus in ("search_spots", "spots_page")
        else []
    )
    from datetime import date, timedelta

    weather = w.get("weather")
    if not w.get("turn_weather_updated") and focus != "weather":
        weather = None
    if weather and r.get("start_date"):
        end = (
            date.fromisoformat(r["start_date"])
            + timedelta(days=int(r.get("days") or 1))
        ).isoformat()
        weather = {
            **weather,
            "days": [
                d for d in weather.get("days", []) if r["start_date"] <= d["date"] < end
            ],
        }
    from app.travel.journey import next_step

    data = {
        "requirements": r,
        "action": focus,
        "confirmed_prefix": PREFIX.get(),
        "result": result,
        "spots": spots,
        "assistant_goal": w.get("assistant_goal") if w.get("turn_is_chat") else None,
        "recommendation_batch": [
            {
                "id": i,
                "name": w["catalog"][i]["name"],
                "role": w["catalog"][i].get("recommendation_role", "primary"),
            }
            for i in (w.get("spot_search") or {}).get("ids", [])
            if i in w["catalog"]
        ]
        if focus in ("search_spots", "spots_page")
        else [],
        "pending_plan_warning": {"issues": w["pending_plan_warning"]["issues"]}
        if w.get("pending_plan_warning")
        else None,
        "pending_auto_selection": w.get("pending_auto_selection"),
        "auto_selection_running": bool(w.get("auto_selection_run")),
        "auto_selection_result": w.get("auto_selection_result")
        if focus in ("approve_auto_selection", "continue_auto_selection")
        else None,
        "visit_analysis": visit_analysis.current(w),
        "visit_requests": w.get("visit_requests", {}),
        "has_current_plan": bool(w.get("plan") and not w["plan"].get("stale")),
        "foods": [
            w["catalog"][i]
            for i in (w.get("food_query") or {}).get("ids", [])
            if i in w["catalog"]
        ]
        if w.get("turn_food_updated") or focus == "search_foods"
        else [],
        "markets": [
            w["catalog"][i]
            for i in (w.get("food_query") or {}).get("markets", [])
            if i in w["catalog"]
        ]
        if w.get("turn_food_updated")
        else [],
        "plan_revision": (w.get("plan") or {}).get("revision")
        if focus == "optimize_plan"
        else None,
        "selected_spots": [
            w["catalog"][i] for i in w.get("selected_spots", []) if i in w["catalog"]
        ],
        "hotels": [
            w["catalog"][i]
            for i in (w.get("hotel_query") or {}).get("ids", [])
            if i in w["catalog"]
        ][:4]
        if focus == "search_hotels"
        else [],
        "weather": weather,
        "weather_note": w.get("weather_note"),
        "last_question": w.get("last_question", "") if w.get("turn_is_chat") else "",
        "hotel": w.get("hotel"),
        "selected_room": w.get("selected_room"),
        "selected_transport": w.get("selected_transport"),
        "selected_return": w.get("selected_return"),
        "meal_choices": w.get("meal_choices", {}),
        "next_step": next_step(w),
    }
    cid = w.get("ui", {}).get("focus_id")
    if focus == "place_detail":
        data["detail_candidate"] = w.get("catalog", {}).get(cid)
    if focus == "ticket":
        data["ticket_result"] = w.get("tickets", {}).get(cid)
    data["interaction_state"] = prompts.interaction_state(w)
    prompt = prompts.system("reply")

    prefix = PREFIX.get()
    target = re.sub(r"\s+", "", prefix)
    pending = ""
    decided = not bool(target)

    def send(chunk):
        nonlocal pending, decided
        if decided:
            emit(chunk)
            return
        pending += chunk
        normalized = re.sub(r"\s+", "", pending)
        if target.startswith(normalized) and len(normalized) < len(target):
            return
        decided = True
        emit(without_repeated_prefix(pending, prefix))
        pending = ""

    answer, usage = await llm_stream(
        [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(model_facts(data), ensure_ascii=False),
            },
        ],
        send,
        max_tokens=1800,
    )
    if pending:
        emit(without_repeated_prefix(pending, prefix))
    w["reply_usage"] = usage
    return prefix + without_repeated_prefix(answer, prefix)
