"""One scenic selection may select several real visits, never its container too."""

from app.core.errors import DataError
from app.travel import spot_hierarchy
from app.travel.selections import remove_selection


def choose(w, cid, *, add_only=False):
    info = spot_hierarchy.selection_info(w, cid)
    targets = info["ids"]
    grouped = targets != [cid]
    removed = info["all_selected"] and not add_only
    if removed:
        remove_selection(w, cid)
    else:
        # Validate the entire group before changing any selection or pins.
        containers = {
            parent
            for target in targets
            for parent in spot_hierarchy.ancestors(w.get("catalog", {}), target)
        }
        kept = [i for i in w.get("selected_spots", []) if i not in containers]
        chosen = list(dict.fromkeys(kept + targets))
        if len(chosen) > 120:
            raise DataError("当前选择已超过120个地点，请先确定优先级后分段规划")
        w["selected_spots"] = chosen
        for parent in containers & set(w.get("visit_requests", {})):
            w.setdefault("spot_scope_selections", {})[parent] = [
                target
                for target in chosen
                if parent in spot_hierarchy.ancestors(w["catalog"], target)
            ]
        if grouped:
            w.setdefault("spot_scope_selections", {})[cid] = targets
    w["spots_confirmed"] = False
    return removed, targets if grouped else []
