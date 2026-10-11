"""Conversation policies for UI actions, separate from action execution."""

from app.travel.actions import QUERY_ACTIONS

SELECTION_ACTIONS = {
    "select",
    "select_room",
    "meal_choice",
    "dismiss_spot",
    "spots_page",
    "requirements",
}
QUIET_ACTIONS = QUERY_ACTIONS | SELECTION_ACTIONS | {"visit_schedule"}
NO_COMPOSE_ACTIONS = (
    QUERY_ACTIONS
    | SELECTION_ACTIONS
    | {
        "refresh_routes",
        "review_timeline",
        "adjust_timeline",
        "undo",
        "cancel_auto_selection",
        "approve_plan_warning",
        "cancel_plan_warning",
    }
)
PREVIEW_ACTIONS = {
    "adjust_timeline",
    "select_room",
    "review_timeline",
    "complete_spots",
    "complete_hotel",
    "complete_food",
    "meal_choice",
    "visit_schedule",
    "analyze_visits",
    "approve_auto_selection",
    "continue_auto_selection",
}
AUDIT_ACTIONS = {
    "complete_spots",
    "analyze_visits",
    "visit_schedule",
    "review_timeline",
}


def quiet(action, status):
    return action == "place_detail" or status == "completed" and action in QUIET_ACTIONS
