"""People-dimension constraint examination for a provisional itinerary.

The existing planner already validates *time* (``schedule.conflicts`` for
date / window / capacity, ``visit_analysis.distribution_warnings`` for minute
load, ``pacing.required_rest_issues`` for user-requested rest, and
``opening_hours.check`` for business hours). This module adds the missing
*people* dimension: does the itinerary respect the physical capacity of
elderly travellers and young children in the party?

Design rationale (academic anchors):

* **HiMAP-Travel** (arxiv 2603.04750) -- "Synchronized Global State" enforces
  invariants across the whole plan. ``examine`` aggregates four invariants
  over every day and every provisional row, mirroring that global check.
* **SagaLLM** (arxiv 2503.11951) -- Validation gate before a plan is
  committed; this module is the gate, ``app.planning.reflect`` is the
  transactional retry.

The module is read-only: it never mutates the workspace, only returns a
report. It does NOT register itself into the main pipeline; callers decide
when to invoke it (see ``app.planning.reflect``).
"""

from datetime import date

# ---------------------------------------------------------------------------
# Profile presets. Numbers cite:
#  * 学龄前日步数 6000-8000  -- 光年坐标 lycoo (运动医学综述)
#  * 老人步幅减幅 20%-30%     -- 同上
#  * 单日 POI 数老人小孩 <=2 项/段(早/午/晚) -- Stardrift / 光年坐标
#  * 单日 POI 数普通 <=3 项/段 -- 行业常识
#  * 拆段阈值 >1 万步拆段+酒店午休 -- 光年坐标
# Steps-per-km uses 1300 (成人步幅 ~0.77 m); elderly multiply by 0.7.
# ---------------------------------------------------------------------------
PROFILE_PRESETS = {
    "elderly": {
        "max_poi_per_halfday": 2,
        "max_steps_per_day": 5000,
        "rest_required": True,
        "steps_factor": 0.7,
    },
    "kids": {
        "max_poi_per_halfday": 2,
        "max_steps_per_day": 6000,
        "rest_required": True,
        "steps_factor": 0.85,
    },
    "default": {
        "max_poi_per_halfday": 3,
        "max_steps_per_day": 10000,
        "rest_required": False,
        "steps_factor": 1.0,
    },
}

# Period -> half-day bucket. "any" is conservatively folded into morning so a
# model that leaves the period open is not given a free pass on density.
HALF_DAY = {"morning": "morning", "afternoon": "afternoon", "evening": "evening", "any": "morning"}

# Conversion: straight-line km between adjacent POIs -> steps. 1300 steps/km
# for an average adult; the preset's steps_factor adjusts for profile.
STEPS_PER_KM = 1300
# POIs are not points; visitors walk inside them and take detours. Multiply
# straight-line distance by this to approximate real walking.
DETOUR_FACTOR = 1.5


def infer_profile(requirements):
    """Infer a profile key from party composition when the user did not say so.

    Looks at child_ages (child < 6 triggers kids preset) and companion_notes
    (老人/长辈/老年 triggers elderly). When both match, the stricter of the
    two (elderly, lower step ceiling) wins. Returns one of the keys in
    PROFILE_PRESETS; default when nothing indicates a vulnerable party.
    """
    notes = " ".join(requirements.get("companion_notes") or [])
    ages = requirements.get("child_ages") or []
    has_elderly = any(w in notes for w in ("老人", "长辈", "老年", "年长", "爷爷", "奶奶", "外婆", "外公"))
    has_young_child = any(isinstance(a, (int, float)) and a < 6 for a in ages)
    if has_elderly:
        return "elderly"
    if has_young_child:
        return "kids"
    return "default"


def preset(profile_key):
    """Return the preset dict (defensive copy) for a profile key."""
    return dict(PROFILE_PRESETS.get(profile_key, PROFILE_PRESETS["default"]))


def _group_rows_by_date(rows):
    """rows is the visit_analysis items list; bucket by date."""
    by_date = {}
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        dt = item.get("date")
        if dt:
            by_date.setdefault(dt, []).append(item)
    return by_date


def _poi_distance_km(a, b):
    """Straight-line km between two catalog points, or None when missing.

    Returns None when either point lacks a ``location`` field so a missing
    coordinate is reported as "unknown" rather than silently treated as 0 km.

    Accepts both the native "lng,lat" string format used by the catalog and a
    [lng, lat] list; lists are normalised so callers can pass either without
    touching coordinate_distance.
    """
    from app.travel.journey import coordinate_distance

    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    la, lb = a.get("location"), b.get("location")
    if not la or not lb:
        return None
    if isinstance(la, (list, tuple)):
        la = "%s,%s" % (la[0], la[1])
    if isinstance(lb, (list, tuple)):
        lb = "%s,%s" % (lb[0], lb[1])
    pa, pb = {"location": la}, {"location": lb}
    try:
        return coordinate_distance(pa, pb)
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def _period_density(rows):
    """Count POIs per half-day bucket for one day's rows."""
    counts = {"morning": 0, "afternoon": 0, "evening": 0}
    for item in rows:
        period = HALF_DAY.get(item.get("period", "any"), "morning")
        counts[period] += 1
    return counts


def _day_steps(w, rows, profile_key):
    """Estimate walking steps for one day from adjacent POI distances.

    Adds straight-line distance between consecutive POIs (sorted by period
    then original order), multiplies by detour factor and the profile's step
    factor. Returns an integer estimate or None when no locations are known.
    """
    cat = w.get("catalog", {})
    preset_ = preset(profile_key)
    order = {"morning": 0, "afternoon": 1, "evening": 2, "any": 0}
    points = [
        cat[item["candidate_id"]]
        for item in rows
        if item.get("candidate_id") in cat
    ]
    # Sort by period bucket so we walk morning->afternoon->evening
    points.sort(key=lambda p: order.get(
        next((i.get("period", "any") for i in rows if i.get("candidate_id") == p.get("id")), "any"), 0))
    # A single POI involves no inter-POI walking; report 0 steps, not unknown.
    if len(points) <= 1:
        return 0
    total_km = 0.0
    found_any = False
    for i in range(len(points) - 1):
        d = _poi_distance_km(points[i], points[i + 1])
        if d is not None:
            total_km += d
            found_any = True
    # Multiple POIs but no usable coordinates -> cannot estimate.
    if not found_any:
        return None
    steps = int(total_km * DETOUR_FACTOR * STEPS_PER_KM * preset_["steps_factor"])
    return steps


def _has_midday_rest(w, dt):
    """True when the plan already schedules a midday rest on this date.

    Mirrors the check in pacing.required_rest_issues but without requiring the
    user to have asked for it: we look at the generated events for a
    rest_type == midday entry inside the day window.
    """
    plan = w.get("plan")
    if not plan:
        return False
    days = plan.get("days") or []
    day = next((d for d in days if d.get("date") == dt), None)
    if not day:
        return False
    for event in day.get("events", []):
        if event.get("rest_type") == "midday":
            return True
    return False


def examine(w, rows=None):
    """Run the people-dimension invariants over a provisional itinerary.

    Args:
        w: workspace dict.
        rows: visit_analysis items. When None, ``visit_analysis.preview(w)``.

    Returns:
        list of finding dicts, each:
            {constraint, status, message, severity, date, related_rows}
        status in {"ok", "warn", "unknown"}. severity in {"low","medium","high"}.
        Empty list means no findings (the plan passed all people-dimension
        checks). The module never raises on incomplete data; it returns
        "unknown" instead, mirroring opening_hours.check's conservative style.
    """
    if rows is None:
        from app.planning.visit_analysis import preview
        rows = preview(w)

    profile_key = infer_profile(w.get("requirements") or {})
    preset_ = preset(profile_key)
    by_date = _group_rows_by_date(rows)
    findings = []

    for dt in sorted(by_date):
        day_rows = by_date[dt]
        _check_density(findings, dt, day_rows, preset_, profile_key)
        _check_steps(findings, w, dt, day_rows, preset_, profile_key)
        _check_rest(findings, w, dt, preset_, profile_key)
        _check_opening(findings, w, dt, day_rows)

    # If nothing was flagged, return an explicit clean bill so callers can
    # distinguish "passed" from "no data".
    if not findings:
        findings.append({
            "constraint": "overall",
            "status": "ok",
            "message": "人员维度体检通过:POI 密度、步数估算、午休安排均符合 %s 画像。" % profile_key,
            "severity": "low",
            "date": None,
            "related_rows": [],
            "profile": profile_key,
        })
    return findings


def _check_density(findings, dt, day_rows, preset_, profile_key):
    """Constraint 1: POI count per half-day <= preset ceiling."""
    counts = _period_density(day_rows)
    ceiling = preset_["max_poi_per_halfday"]
    for period, n in counts.items():
        if n > ceiling:
            findings.append({
                "constraint": "poi_density",
                "status": "warn",
                "message": "%s 的 %s 安排了 %d 个 POI,超过 %s 画像上限 %d 项/段。"
                % (dt, period, n, profile_key, ceiling),
                "severity": "high" if profile_key != "default" else "medium",
                "date": dt,
                "related_rows": [r.get("candidate_id") for r in day_rows if HALF_DAY.get(r.get("period", "any")) == period],
                "profile": profile_key,
                "ceiling": ceiling,
                "actual": n,
            })


def _check_steps(findings, w, dt, day_rows, preset_, profile_key):
    """Constraint 2: estimated walking steps per day <= preset ceiling."""
    steps = _day_steps(w, day_rows, profile_key)
    if steps is None:
        findings.append({
            "constraint": "walking_steps",
            "status": "unknown",
            "message": "%s 的景点缺少坐标,无法估算步行步数;有坐标后可重新体检。" % dt,
            "severity": "low",
            "date": dt,
            "related_rows": [r.get("candidate_id") for r in day_rows],
            "profile": profile_key,
        })
        return
    ceiling = preset_["max_steps_per_day"]
    if steps > ceiling:
        findings.append({
            "constraint": "walking_steps",
            "status": "warn",
            "message": "%s 估算步行约 %d 步,超过 %s 画像上限 %d 步。建议拆段或加酒店午休。"
            % (dt, steps, profile_key, ceiling),
            "severity": "high" if profile_key != "default" else "medium",
            "date": dt,
            "related_rows": [r.get("candidate_id") for r in day_rows],
            "profile": profile_key,
            "ceiling": ceiling,
            "actual": steps,
        })


def _check_rest(findings, w, dt, preset_, profile_key):
    """Constraint 3: vulnerable profiles (elderly / kids) should have midday rest.

    Unlike pacing.required_rest_issues which only fires when the user
    explicitly asks for rest, this checks the profile-implied need. If the
    user did ask for midday_rest_minutes, pacing already covers it; here we
    catch the silent case.
    """
    if not preset_["rest_required"]:
        return
    # If the user explicitly requested rest, pacing.required_rest_issues owns
    # that check; skip to avoid double-warning.
    if w.get("requirements", {}).get("midday_rest_minutes"):
        return
    if not _has_midday_rest(w, dt):
        findings.append({
            "constraint": "midday_rest_missing",
            "status": "warn",
            "message": "%s 未安排午休,%s 画像建议安排 30-60 分钟午休以恢复体力。" % (dt, profile_key),
            "severity": "medium",
            "date": dt,
            "related_rows": [],
            "profile": profile_key,
        })


def _check_opening(findings, w, dt, day_rows):
    """Constraint 4: aggregate opening-hours check (reuses opening_hours.check).

    opening_hours.check already exists; we call it here so the people-dimension
    report is self-contained and the source is attributed. This is not a
    reimplementation -- it delegates.

    We use a conservative half-day bucket start (09:00 / 13:00 / 18:00) rather
    than querying schedule.windows so this module stays independent of the
    transport/hotel import chain. A warn here means "even at the earliest
    plausible bucket start it does not fit".
    """
    from app.planning import opening_hours

    cat = w.get("catalog", {})
    # Conservative arrival per half-day bucket, independent of schedule.windows.
    bucket_start = {"morning": 9 * 60, "afternoon": 13 * 60, "evening": 18 * 60}
    for item in day_rows:
        p = cat.get(item.get("candidate_id"))
        if not p:
            continue
        opening = p.get("opening")
        if not opening:
            continue
        bucket = HALF_DAY.get(item.get("period", "any"), "morning")
        start = bucket_start.get(bucket, 9 * 60)
        ok, message, _limit = opening_hours.check(
            opening, p.get("name", ""), start, item.get("duration", 90), dt
        )
        if not ok:
            finding = {
                "constraint": "opening_hours",
                "status": "warn",
                "message": "%s %s:%s" % (dt, p.get("name", ""), message),
                "severity": "medium",
                "date": dt,
                "related_rows": [item.get("candidate_id")],
                "source": "opening_hours.check (reused)",
            }
            # 同一条通道里区分"当天闭馆"与"超出开放时段"
            if opening_hours.closed_today(opening, dt):
                finding["closed_on_weekday"] = True
                finding["closure_strength"] = opening_hours.closed_day_strength(opening, dt)
            findings.append(finding)
