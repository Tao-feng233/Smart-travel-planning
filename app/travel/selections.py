"""Remove canonical choices and their dependent assignments together."""

from app.travel.requirements import mark_stale


def remove_selection(w, candidate_id):
    changed = False
    from app.travel.spot_hierarchy import ancestors

    cat = w.get("catalog", {})
    spot_ids = {
        cid
        for cid in w.get("selected_spots", [])
        if cid == candidate_id or candidate_id in ancestors(cat, cid)
    }
    if spot_ids:
        w["selected_spots"] = [
            cid for cid in w["selected_spots"] if cid not in spot_ids
        ]
        w["spots_confirmed"] = False
        for cid in spot_ids | {candidate_id}:
            w.get("visit_requests", {}).pop(cid, None)
        if "visit_order" in w:
            w["visit_order"] = [
                cid for cid in w["visit_order"] if cid not in spot_ids | {candidate_id}
            ]
        changed = True
    if "spot_scope_selections" in w:
        w["spot_scope_selections"] = {
            parent: ids
            for parent, ids in w["spot_scope_selections"].items()
            if parent != candidate_id
            and candidate_id not in ancestors(cat, parent)
            and any(cid in w.get("selected_spots", []) for cid in ids)
        }
    if "meal_choices" in w:
        kept = {
            key: value
            for key, value in w["meal_choices"].items()
            if value.get("food_id") != candidate_id
        }
        if kept != w["meal_choices"]:
            w["meal_choices"] = kept
            w["dining_reviewed"] = False
            changed = True
    stays = w.get("stay_hotels") or {}
    removed_nights = {
        day for day, hotel_id in stays.items() if hotel_id == candidate_id
    }
    if removed_nights:
        w["stay_hotels"] = {
            day: hotel_id
            for day, hotel_id in stays.items()
            if day not in removed_nights
        }
        changed = True
    if (w.get("hotel") or {}).get("id") == candidate_id:
        w["hotel"] = None
        if (w.get("selected_room") or {}).get("hotel_id") in (None, candidate_id):
            w["selected_room"] = None
        changed = True
    if (w.get("selected_room") or {}).get("hotel_id") == candidate_id:
        w["selected_room"] = None
        changed = True
    if "selected_rooms" in w:
        rooms = w["selected_rooms"]
        kept = {
            hotel_id: room
            for hotel_id, room in rooms.items()
            if hotel_id != candidate_id and room.get("hotel_id") != candidate_id
        }
        changed = changed or kept != rooms
        w["selected_rooms"] = kept
    for slot in ("selected_transport", "selected_return"):
        if (w.get(slot) or {}).get("id") == candidate_id:
            w[slot] = None
            changed = True
    if changed:
        mark_stale(w)
    return changed
