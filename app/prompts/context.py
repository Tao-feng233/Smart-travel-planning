"""Model-visible facts derived from current business services."""


def interaction_state(w):
    """Expose optional choices and explicit-vs-suggested constraints as facts."""
    from app.travel.discovery import recommendation_minimum, MAX_RECOMMENDATIONS
    from app.travel.spot_candidates import BATCH_SIZE

    r = w.get("requirements") or {}
    rest = r.get("midday_rest_minutes")
    hotel = w.get("hotel") or {}
    transport = w.get("selected_transport") or {}
    arrival = transport.get("arrival")
    return {
        "recommendation_policy": {
            "target": recommendation_minimum(w, {}),
            "batch_size": BATCH_SIZE,
            "maximum": MAX_RECOMMENDATIONS,
            "all_candidates_required_to_visit": False,
            "ranking": "偏好、代表景点资料、地图评分与位置；无实时热度排行",
        },
        "optional_choices": ["hotel_room", "intercity_tickets", "restaurant"],
        "hotel": {
            "selected": bool(hotel),
            "room_selected": bool(w.get("selected_room")),
            "quote_needs_refresh": bool(hotel.get("stale") or hotel.get("quote_stale")),
            "location_needs_check": bool(
                hotel.get("location_stale") or hotel.get("selection_stale")
            ),
            "checkin_time_confirmed_by_selection": False,
        },
        "rest": {
            "source": "user" if rest is not None else "suggested",
            "minutes": rest,
            "required": isinstance(rest, (int, float)) and rest > 0,
            "cancelled": rest == 0 or bool(r.get("cancel_rest")),
        },
        "arrival_time": {
            "value": arrival,
            "status": "confirmed"
            if arrival and transport.get("selection_status") == "confirmed"
            else "suggested"
            if arrival
            else "unknown",
        },
        "plan_status": "current"
        if w.get("plan") and not w["plan"].get("stale")
        else "stale"
        if w.get("plan")
        else "absent",
        "planning_warning_pending": bool(w.get("pending_plan_warning")),
        "selection_confirmation_pending": bool(w.get("pending_auto_selection")),
    }
