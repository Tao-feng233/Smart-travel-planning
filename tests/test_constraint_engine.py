"""Unit tests for constraint_engine: people-dimension checks, no real API."""

from app.planning import constraint_engine


# ---------------------------------------------------------------------------
# infer_profile
# ---------------------------------------------------------------------------

def test_infer_profile_elderly_from_notes():
    req = {"companion_notes": ["带老人出行", "慢节奏"]}
    assert constraint_engine.infer_profile(req) == "elderly"


def test_infer_profile_elderly_keywords():
    for word in ("老人", "长辈", "老年", "年长", "爷爷", "奶奶", "外婆", "外公"):
        assert constraint_engine.infer_profile({"companion_notes": [word]}) == "elderly"


def test_infer_profile_kids_from_young_child():
    req = {"child_ages": [3, 5]}
    assert constraint_engine.infer_profile(req) == "kids"


def test_infer_profile_kids_threshold_is_six():
    # age 6 is not "young child"; age 5 is
    assert constraint_engine.infer_profile({"child_ages": [6]}) == "default"
    assert constraint_engine.infer_profile({"child_ages": [5]}) == "kids"


def test_infer_profile_elderly_wins_over_kids():
    # When both an elderly note and a young child are present, elderly
    # (the stricter, lower step ceiling) wins.
    req = {"companion_notes": ["老人"], "child_ages": [3]}
    assert constraint_engine.infer_profile(req) == "elderly"


def test_infer_profile_default_when_no_vulnerable_party():
    assert constraint_engine.infer_profile({}) == "default"
    assert constraint_engine.infer_profile({"child_ages": [8]}) == "default"


# ---------------------------------------------------------------------------
# examine: poi_density
# ---------------------------------------------------------------------------

def _base_workspace(profile="default"):
    """A minimal workspace that does not crash examine's helpers."""
    return {
        "requirements": (
            {"companion_notes": ["老人"]} if profile == "elderly"
            else {"child_ages": [4]} if profile == "kids"
            else {}
        ),
        "catalog": {},
    }


def test_examine_density_warns_elderly_three_morning_pois():
    w = _base_workspace("elderly")
    w["catalog"] = {
        "p1": {"id": "p1", "name": "A"},
        "p2": {"id": "p2", "name": "B"},
        "p3": {"id": "p3", "name": "C"},
    }
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p3", "date": "2026-10-13", "period": "morning", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    densities = [f for f in report if f["constraint"] == "poi_density"]
    assert len(densities) == 1
    assert densities[0]["status"] == "warn"
    assert densities[0]["actual"] == 3
    assert densities[0]["ceiling"] == 2
    assert densities[0]["profile"] == "elderly"


def test_examine_density_ok_default_three_morning_pois():
    # default ceiling is 3, so 3 morning POIs is fine
    w = _base_workspace("default")
    w["catalog"] = {
        "p1": {"id": "p1"}, "p2": {"id": "p2"}, "p3": {"id": "p3"},
    }
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p3", "date": "2026-10-13", "period": "morning", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    assert not any(f["constraint"] == "poi_density" and f["status"] == "warn" for f in report)


def test_examine_density_per_halfday_not_cross_day():
    # 2 morning + 2 afternoon is fine for elderly (ceiling 2 per half-day)
    w = _base_workspace("elderly")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}, "p3": {"id": "p3"}, "p4": {"id": "p4"}}
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p3", "date": "2026-10-13", "period": "afternoon", "duration": 90},
        {"candidate_id": "p4", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    assert not any(f["constraint"] == "poi_density" and f["status"] == "warn" for f in report)


# ---------------------------------------------------------------------------
# examine: walking_steps
# ---------------------------------------------------------------------------

def test_examine_steps_unknown_without_location():
    w = _base_workspace("elderly")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}}
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    steps = [f for f in report if f["constraint"] == "walking_steps"]
    assert len(steps) == 1
    assert steps[0]["status"] == "unknown"


def test_examine_steps_warns_when_far_apart():
    w = _base_workspace("elderly")
    # ~10km between the two points; elderly ceiling 5000 steps
    w["catalog"] = {
        "p1": {"id": "p1", "location": [116.40, 39.90]},  # Beijing
        "p2": {"id": "p2", "location": [116.50, 39.99]},  # ~12km away
    }
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    steps = [f for f in report if f["constraint"] == "walking_steps" and f["status"] == "warn"]
    assert len(steps) == 1
    assert steps[0]["actual"] > 5000


# ---------------------------------------------------------------------------
# examine: midday_rest_missing
# ---------------------------------------------------------------------------

def test_examine_rest_warns_elderly_without_midday_rest():
    w = _base_workspace("elderly")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}}
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    rests = [f for f in report if f["constraint"] == "midday_rest_missing"]
    assert len(rests) == 1
    assert rests[0]["status"] == "warn"


def test_examine_rest_skipped_when_user_requested_rest():
    # When the user explicitly asked for midday_rest_minutes, pacing owns it.
    w = _base_workspace("elderly")
    w["requirements"]["midday_rest_minutes"] = 60
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}}
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    assert not any(f["constraint"] == "midday_rest_missing" for f in report)


def test_examine_rest_skipped_for_default_profile():
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}}
    rows = [{"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90}]
    report = constraint_engine.examine(w, rows)
    assert not any(f["constraint"] == "midday_rest_missing" for f in report)


def test_examine_rest_ok_when_plan_has_midday_event():
    w = _base_workspace("elderly")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}}
    w["plan"] = {"days": [{"date": "2026-10-13", "events": [{"rest_type": "midday"}]}]}
    rows = [
        {"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90},
        {"candidate_id": "p2", "date": "2026-10-13", "period": "afternoon", "duration": 90},
    ]
    report = constraint_engine.examine(w, rows)
    assert not any(f["constraint"] == "midday_rest_missing" for f in report)


# ---------------------------------------------------------------------------
# examine: overall
# ---------------------------------------------------------------------------

def test_examine_returns_overall_ok_when_clean():
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}}
    rows = [{"candidate_id": "p1", "date": "2026-10-13", "period": "morning", "duration": 90}]
    report = constraint_engine.examine(w, rows)
    assert any(f["constraint"] == "overall" and f["status"] == "ok" for f in report)


def test_examine_handles_empty_rows():
    w = _base_workspace("default")
    report = constraint_engine.examine(w, [])
    assert any(f["status"] == "ok" for f in report)
