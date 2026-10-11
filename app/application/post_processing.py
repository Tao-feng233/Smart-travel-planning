"""Refresh estimates and audits after a successful business action."""

from app.application.action_policy import PREVIEW_ACTIONS, AUDIT_ACTIONS
from app.application.turn_state import choice_signature, audit_signature


async def refresh(workspace, baseline, performed, selected_kind, progress, model):
    from app.travel.foods import prune_unavailable

    # Preserve the existing advisory cleanup boundary; an unavailable estimate
    # must not discard an otherwise successful selection.
    try:
        prune_unavailable(workspace)
    except Exception:
        pass
    if (
        tuple(workspace.get("selected_spots", [])) != baseline.spots
        or performed in PREVIEW_ACTIONS
        or selected_kind in ("hotel", "train", "flight")
        or choice_signature(workspace) != baseline.choices
    ):
        from app.planning.travel_preview import refresh as preview

        # Ordinary selections use program estimates. Only an explicit request
        # invokes the scheduling model; generating the book owns final scheduling.
        await preview(
            workspace,
            progress,
            model=model
            if performed in ("adjust_timeline", "review_timeline", "refresh_routes")
            else None,
            optimize=performed == "adjust_timeline",
        )
    if baseline.audit != audit_signature(workspace) or performed in AUDIT_ACTIONS:
        from app.planning.timeline_review import refresh as audit

        return await audit(
            workspace,
            model,
            progress,
            model_review=performed in ("review_timeline", "adjust_timeline"),
        )
    return None
