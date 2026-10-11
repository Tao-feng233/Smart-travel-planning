"""Route each action to one owner; preserve common coverage/UI setup."""

from app.core.errors import DataError
from app.application import guidance
from app.travel.handlers import (
    assistant,
    planning,
    context,
    dining,
    places,
    spots,
    lodging,
    transport,
)

HANDLERS = {
    "request_auto_selection": assistant.do_request_auto_selection,
    "arrange_remaining": assistant.do_arrange_remaining,
    "undo": assistant.do_undo,
    "approve_auto_selection": assistant.do_approve_auto_selection,
    "continue_auto_selection": assistant.do_approve_auto_selection,
    "cancel_auto_selection": assistant.do_cancel_auto_selection,
    "optimize_plan": planning.do_optimize_plan,
    "approve_plan_warning": planning.do_approve_plan_warning,
    "cancel_plan_warning": planning.do_approve_plan_warning,
    "chat": context.do_chat,
    "adjust_timeline": planning.do_adjust_timeline,
    "review_timeline": planning.do_review_timeline,
    "refresh_routes": planning.do_refresh_routes,
    "visit_schedule": planning.do_visit_schedule,
    "analyze_visits": planning.do_analyze_visits,
    "complete_food": dining.do_complete_food,
    "requirements": context.do_requirements,
    "search_foods": dining.do_search_foods,
    "meal_choice": dining.do_meal_choice,
    "select_room": lodging.do_select_room,
    "place_detail": places.do_place_detail,
    "discover_destinations": spots.do_discover_destinations,
    "choose_destination": spots.do_choose_destination,
    "complete_spots": spots.do_complete_spots,
    "transport_arrangement": transport.do_transport_arrangement,
    "complete_hotel": lodging.do_complete_hotel,
    "skip_hotel": lodging.do_complete_hotel,
    "dismiss_spot": spots.do_dismiss_spot,
    "select": places.do_select,
    "hotel_detail": lodging.do_hotel_detail,
    "search_spots": spots.do_search_spots,
    "spots_page": spots.do_spots_page,
    "search_hotels": lodging.do_search_hotels,
    "weather": context.do_weather,
    "train": transport.do_train,
    "flight": transport.do_train,
    "ticket": spots.do_ticket,
    "plan": planning.do_plan,
}

DIRECT_ACTIONS = frozenset(
    {
        "continue_auto_selection",
        "adjust_timeline",
        "approve_plan_warning",
        "undo",
        "chat",
        "complete_food",
        "cancel_plan_warning",
        "cancel_auto_selection",
        "request_auto_selection",
        "review_timeline",
        "visit_schedule",
        "arrange_remaining",
        "refresh_routes",
        "approve_auto_selection",
        "optimize_plan",
        "analyze_visits",
    }
)

CITY_REQUIRED_ACTIONS = frozenset(
    {
        "search_spots",
        "flight",
        "weather",
        "train",
        "spots_page",
        "ticket",
        "plan",
        "search_hotels",
    }
)


async def dispatch(w, action, args, progress, services):
    w.setdefault("catalog", {})
    if action in ("search_spots", "search_hotels", "search_foods") and w[
        "requirements"
    ].get("city"):
        from app.knowledge.coverage import require_city

        require_city(w["requirements"]["city"])
    if action not in DIRECT_ACTIONS:
        w["ui"] = guidance.describe(w, action, args, status="loading")
        progress(w["ui"]["title"])
    handler = HANDLERS.get(action)
    if (action in CITY_REQUIRED_ACTIONS or handler is None) and not w[
        "requirements"
    ].get("city"):
        raise DataError("先告诉我想去哪个城市；还没想好也可以先聊旅行偏好。")
    if handler is None:
        raise DataError("暂不支持这个操作")
    return await handler(w, action, args, progress, services)
