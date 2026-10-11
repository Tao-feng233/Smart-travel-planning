"""Model input facts, independent of model invocation and state mutations."""

from datetime import date
from app import prompts
from app.agents.goals import plan_context
from app.travel import discovery, journey
from app.travel.choices import room_choices


def intent_context(w, text):
    visible_ids = (
        list(discovery.page_info(w)["ids"])
        + list((w.get("hotel_query") or {}).get("ids", []))
        + list((w.get("food_query") or {}).get("ids", []))
        + [p["id"] for p in (w.get("transport") or {}).get("items", [])]
        + w["selected_spots"]
    )
    visible_ids += [
        p["id"]
        for p in (w.get("hotel"), w.get("selected_transport"), w.get("selected_return"))
        if p and p.get("id")
    ]

    from app.knowledge.coverage import snapshot, canonical_city

    coverage = snapshot()
    context = {
        "covered_cities": [x["name"] for x in coverage["cities"].values()],
        "covered_spots": sorted(
            coverage["names"].get(canonical_city(w["requirements"].get("city")), set())
        ),
        "current_view": w.get("ui", {}).get("view"),
        "today": date.today().isoformat(),
        "requirements": w["requirements"],
        "selected_spots": w["selected_spots"],
        "next_step": journey.next_step(w),
        "visit_requests": w.get("visit_requests", {}),
        "selected_meals": w.get("meal_choices", {}),
        "food_query": w.get("food_query"),
        "meal_dates": journey.meal_dates(w),
        "default_return_date": journey.travel_date(w),
        "last_action": w.get("last_action"),
        "room_choices": [
            p
            for h in w.get("catalog", {}).values()
            if h.get("kind") == "hotel" and not h.get("stale")
            for p in room_choices(h, w["requirements"])
        ],
        "selected_room": w.get("selected_room"),
        "hotel": w.get("hotel"),
        "selected_transport": w.get("selected_transport"),
        "selected_return": w.get("selected_return"),
        "catalog": [
            {
                k: x.get(k)
                for k in (
                    "id",
                    "name",
                    "kind",
                    "address",
                    "opening",
                    "price",
                    "price_basis",
                    "source",
                    "recommendation",
                )
            }
            for cid in dict.fromkeys(visible_ids)
            if cid in w.get("catalog", {})
            for x in [w["catalog"][cid]]
        ],
        "official_guides": w.get("rag_results", []),
        "plan_summary": plan_context(w),
        "previous_goal": w.get("assistant_goal"),
        "has_current_plan": bool(w.get("plan") and not w["plan"].get("stale")),
        "current_spot_page": w.get("spot_search", {}),
        "spot_preference": w.get("spot_preference"),
        "destinations": w.get("destinations", []),
        "recent_messages": w["messages"][-6:],
        "user_message": text,
    }
    context["interaction_state"] = prompts.interaction_state(w)

    return context
