"""Resolve owned workspaces and assemble the existing browser contract."""

from app.application import guidance
from app.travel import discovery
from app.persistence import storage


def present(w):
    from app.travel.choices import room_choices
    from app.travel.price_hints import hint
    from app.travel.spot_hierarchy import state, duplicate_plan

    if w.get("plan") and duplicate_plan(w):
        w["plan"]["stale"] = True
    for p in w.get("catalog", {}).values():
        if p.get("kind") == "hotel" and p.get("detail") and not p.get("stale"):
            p["room_choices"] = room_choices(p, w["requirements"])
        if p.get("kind") in ("spot", "food"):
            p["price_hint"] = hint(w, p)
    active = storage.active_job(w["id"])
    if not active and w.get("ui", {}).get("status") == "loading":
        guidance.finish(w, "interrupted")
    from app.travel.journey import next_step
    from app.travel.journey import selection_assessment, is_local
    from app.planning.schedule import build
    from app.travel import stay_plan

    # 逐晚住宿下发：行的候选（candidate_ids 等）来自已发布的那一份，不能重算——重算会把
    # 已查到的候选丢掉。分配与未选夜晚则按当前选择重新推导，避免旧行内 hotel_source 过时
    # 让"已选好的一晚"显示成尚未选（折叠也随之失效）。
    stay = stay_plan.merge_plan(w, stay_plan.plan(w), w.get("stay_plan"))
    stay.update(
        assignments=stay_plan.assignment_view(w), unassigned=stay_plan.unassigned(w)
    )
    from app.planning.timeline_review import current as current_review

    return {
        **w,
        "timeline_review": current_review(w),
        "stay_plan": stay,
        "spot_coverage": state(w),
        "timeline": build(w),
        "active_job": active,
        "next_step": next_step(w),
        "selection_assessment": selection_assessment(w),
        "local_trip": is_local(w["requirements"]),
        **(
            {"spot_page": discovery.page_info(w), "spot_groups": discovery.groups(w)}
            if w.get("spot_search")
            else {}
        ),
    }
