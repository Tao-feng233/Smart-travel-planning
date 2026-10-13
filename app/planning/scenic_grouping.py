"""Soft same-scope preferences, subordinate to dates, periods and time budgets."""

from app.travel.spot_hierarchy import scenic_groups, state


def membership(w):
    result = {}
    for group in scenic_groups(w):
        for cid in group["candidate_ids"]:
            result.setdefault(cid, group["parent_id"])
    return result


def batches(w, spots, limit=16):
    """Avoid splitting a small scenic group at a model batch boundary."""
    scopes = membership(w)
    units = {}
    for spot in spots:
        units.setdefault(scopes.get(spot["id"], spot["id"]), []).append(spot)
    result = []
    current = []
    for unit in units.values():
        if current and len(current) + len(unit) > limit:
            result.append(current)
            current = []
        while len(unit) > limit:
            result.append(unit[:limit])
            unit = unit[limit:]
        current.extend(unit)
    if current:
        result.append(current)
    return result


def together(w, items, budgets):
    """Cluster fallback estimates only when a whole group fits without overload."""
    result = [dict(item) for item in items]
    by_id = {item["candidate_id"]: item for item in result}
    pins = state(w)["visit_requests"]
    for group in scenic_groups(w):
        members = [by_id[cid] for cid in group["candidate_ids"] if cid in by_id]
        if len(members) < 2 or len({i["date"] for i in members}) == 1:
            continue
        fixed = {
            pins[i["candidate_id"]]["date"]
            for i in members
            if pins.get(i["candidate_id"], {}).get("date")
        }
        if len(fixed) > 1:
            continue
        ids = {i["candidate_id"] for i in members}
        choices = []
        for dt, budget in budgets.items():
            if fixed and dt not in fixed:
                continue
            load = sum(
                i["duration"] + budget["transfer_buffer_minutes"]
                for i in result
                if i["date"] == dt and i["candidate_id"] not in ids
            )
            total = load + sum(
                i["duration"] + budget["transfer_buffer_minutes"] for i in members
            )
            if total <= budget["visit_minutes"]:
                choices.append((total / max(1, budget["visit_minutes"]), dt))
        if not choices:
            continue
        dt = min(choices)[1]
        for item in members:
            if item["date"] != dt:
                item["date"] = dt
                item["period"] = pins.get(item["candidate_id"], {}).get("period", "any")
    return result


def split_advice(w, items, budgets):
    """Ask the model to reconsider avoidable splits; these are not user errors."""
    clustered = {i["candidate_id"]: i["date"] for i in together(w, items, budgets)}
    return [
        {
            "code": "scenic_group_split",
            "level": "advisory",
            "candidate_ids": group["candidate_ids"],
            "message": group["name"]
            + "内部地点分散在不同日期，估算存在同日可容纳的安排；优先合并并核对交通、开放和固定条件，确有原因再拆分。",
        }
        for group in scenic_groups(w)
        if any(
            clustered.get(i["candidate_id"]) != i["date"]
            for i in items
            if i["candidate_id"] in group["candidate_ids"]
        )
    ]


def ordered(w, items):
    """Keep flexible siblings adjacent within each period; explicit order wins."""
    if w.get("visit_order") or any(i.get("sequence") is not None for i in items):
        return items
    scopes = membership(w)
    first = {}
    for index, item in enumerate(items):
        key = scopes.get(item["candidate_id"], item["candidate_id"])
        first.setdefault(key, index)
    return sorted(
        items,
        key=lambda i: (
            {"morning": 0, "any": 1, "afternoon": 2, "evening": 3}.get(
                i.get("period", "any"), 1
            ),
            first[scopes.get(i["candidate_id"], i["candidate_id"])],
        ),
    )
