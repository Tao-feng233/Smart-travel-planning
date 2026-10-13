"""Commit one business action only after it returns successfully."""

import copy
from contextvars import ContextVar
from app.core.errors import DataError

QUERY_PREVIEW = ContextVar("travel_query_preview", default=None)
QUERY_ACTIONS = {
    "search_spots",
    "search_hotels",
    "search_foods",
    "weather",
    "train",
    "flight",
    "ticket",
    "place_detail",
    "hotel_detail",
}


def commit(workspace, draft):
    # Callers may hold this goal while executing several steps. Keep its identity,
    # while still copying it during execution so failed edits cannot change it.
    goal = workspace.get("assistant_goal")
    updated = draft.get("assistant_goal")
    if goal is not None and updated is not None:
        goal.clear()
        goal.update(updated)
        draft["assistant_goal"] = goal
    workspace.clear()
    workspace.update(draft)


async def run(workspace, action, arguments, progress, handler):
    draft = copy.deepcopy(workspace)
    preview_token = QUERY_PREVIEW.set(draft if action in QUERY_ACTIONS else None)
    try:
        result = await handler(draft, action, arguments, progress)
    except DataError:
        # Query-failure markers are observations; retain them without publishing
        # partial edits or overwriting previously cached facts.
        if action == "place_detail":
            cid = arguments.get("id")
            old = workspace.get("catalog", {}).get(cid)
            observed = draft.get("catalog", {}).get(cid) or {}
            if (
                old is not None
                and observed.get("place_detail_status") == "query_failed"
            ):
                for key in ("place_detail_status", "place_detail_checked_at"):
                    if key in observed:
                        old[key] = observed[key]
        raise
    finally:
        QUERY_PREVIEW.reset(preview_token)
    commit(workspace, draft)
    return result


async def apply_choices(workspace, intent, progress, handler):
    from app.core.errors import DataError
    from app.travel.selections import remove_selection

    selected = intent.get("select_ids") or []
    removed = intent.get("remove_ids") or []
    if not selected and not removed:
        return ""
    draft = copy.deepcopy(workspace)
    directions = []
    for cid in selected + removed:
        if cid not in draft.get("catalog", {}):
            raise DataError("模型引用了不存在的候选，请先查询真实候选。")
    for cid in selected:
        place = draft["catalog"][cid]
        if place.get("stale"):
            raise DataError("候选条件已变化，请重新查询后选择。")
        if place.get("kind") in ("train", "flight"):
            directions.append(place.get("direction", "outbound"))
    if len(directions) != len(set(directions)):
        raise DataError("同一方向只能选择一个班次，请明确要保留哪一个。")
    for cid in removed:
        remove_selection(draft, cid)
    answers = []
    slots = {
        key: intent[key]
        for key in (
            "stay_date",
            "stay_dates",
            "meal_date",
            "meal_period",
            "meal_mode",
            "replace",
        )
        if key in intent
    }
    for cid in selected:
        if draft["catalog"][cid].get("kind") == "spot":
            from app.travel.spot_hierarchy import selection_info

            info = selection_info(draft, cid)
            if info["all_selected"] and (
                info["ids"] == [cid] or cid in draft.get("spot_scope_selections", {})
            ):
                continue
        answers.append(
            await handler(
                draft, "select", {"id": cid, **slots, "add_only": True}, progress
            )
        )
    commit(workspace, draft)
    return "\n".join(answer for answer in answers if answer)
