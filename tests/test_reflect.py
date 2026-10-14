"""Unit tests for reflect: the people-dimension refine loop, no real API."""

import asyncio
import json

from app.planning import reflect


# ---------------------------------------------------------------------------
# helpers
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


def _row(cid, period="morning", date="2026-10-13", duration=90):
    return {"candidate_id": cid, "date": date, "period": period, "duration": duration}


def _seed_visit_analysis(w, rows):
    """Seed the cached visit_analysis so examine(w) resolves to ``rows``.

    review_and_refine always opens with findings(w) -- rows=None -- which
    falls through to visit_analysis.preview(w). Seeding the cache is the
    documented way the workspace carries an already-computed plan:
    current(w) only accepts a value whose signature matches the workspace,
    so the real signature is stamped here. Lazy import keeps module import
    light, matching constraint_engine's own style.
    """
    from app.planning.visit_analysis import signature

    w["visit_analysis"] = {
        "signature": signature(w),
        "items": rows,
        "status": "model",
        "notices": [],
    }
    return w


def _crowded_elderly_workspace():
    """3 morning POIs on 2026-10-13 -> poi_density warn.

    The plan carries a midday rest so the only unsatisfied constraint is
    density; this keeps the "converged" round reachable by dropping POIs.
    """
    w = _base_workspace("elderly")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}, "p3": {"id": "p3"}}
    w["plan"] = {"days": [{"date": "2026-10-13", "events": [{"rest_type": "midday"}]}]}
    return _seed_visit_analysis(w, [_row("p1"), _row("p2"), _row("p3")])


# ---------------------------------------------------------------------------
# needs_refine
# ---------------------------------------------------------------------------

def test_needs_refine_false_for_clean_report():
    # examine never returns []: a clean plan is one overall/ok finding.
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}}
    report = reflect.findings(w, [_row("p1")])
    assert len(report) == 1
    assert report[0]["constraint"] == "overall"
    assert report[0]["status"] == "ok"
    assert reflect.needs_refine(report) is False


def test_needs_refine_ignores_unknown_status():
    # walking_steps "unknown" (missing coordinates) is not a warn, so it must
    # not drag the plan into a refinement round.
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}, "p2": {"id": "p2"}}
    report = reflect.findings(w, [_row("p1", "morning"), _row("p2", "afternoon")])
    steps = [f for f in report if f["constraint"] == "walking_steps"]
    assert len(steps) == 1
    assert steps[0]["status"] == "unknown"
    assert reflect.needs_refine(report) is False


def test_needs_refine_true_when_any_warn():
    w = _crowded_elderly_workspace()
    report = reflect.findings(w)
    densities = [f for f in report if f["constraint"] == "poi_density"]
    assert len(densities) == 1
    assert densities[0]["status"] == "warn"
    assert reflect.needs_refine(report) is True


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_none_when_report_is_clean():
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}}
    report = reflect.findings(w, [_row("p1")])
    assert reflect.build_prompt(report) is None


def test_build_prompt_serialises_only_violations():
    w = _crowded_elderly_workspace()
    prompt = reflect.build_prompt(reflect.findings(w))
    assert prompt is not None
    payload = json.loads(prompt)
    assert payload["max_rounds"] == 2
    names = [v["constraint"] for v in payload["violations"]]
    assert "poi_density" in names
    # unknown findings are informational, not violations to fix
    assert "walking_steps" not in names
    assert payload["violations"][0]["date"] == "2026-10-13"


# ---------------------------------------------------------------------------
# review_and_refine: 0 violations
# ---------------------------------------------------------------------------

def test_review_and_refine_clean_plan_never_calls_regenerate():
    w = _base_workspace("default")
    w["catalog"] = {"p1": {"id": "p1"}}
    _seed_visit_analysis(w, [_row("p1")])
    calls = []

    async def regenerate(workspace):
        calls.append(workspace)
        return [_row("p1")]

    report, rounds = asyncio.run(reflect.review_and_refine(w, regenerate))
    assert rounds == 0
    assert calls == []
    assert len(report) == 1
    assert report[0]["constraint"] == "overall"
    assert report[0]["status"] == "ok"
    # no prompt to hand over, so the scratch field is never created
    assert reflect.build_prompt(report) is None
    assert "_constraint_refinement" not in w


# ---------------------------------------------------------------------------
# review_and_refine: converges in 1 round
# ---------------------------------------------------------------------------

def test_review_and_refine_converges_in_one_round():
    w = _crowded_elderly_workspace()
    calls = []
    seen = []

    async def regenerate(workspace):
        calls.append(1)
        # the loop must have parked the prompt on the workspace first
        seen.append(list(workspace.get("_constraint_refinement", [])))
        return [_row("p1")]  # 1 morning POI -> within the elderly ceiling

    report, rounds = asyncio.run(reflect.review_and_refine(w, regenerate))
    assert rounds == 1
    assert len(calls) == 1
    assert len(seen[0]) == 1
    assert seen[0][0]["round"] == 1
    assert "poi_density" in seen[0][0]["prompt"]
    # converged: the final report is the clean bill of health
    assert len(report) == 1
    assert report[0]["constraint"] == "overall"
    assert report[0]["status"] == "ok"
    # scratch field must not leak into the workspace
    assert "_constraint_refinement" not in w


# ---------------------------------------------------------------------------
# review_and_refine: not converged -> truncated at 2 rounds
# ---------------------------------------------------------------------------

def test_review_and_refine_truncates_at_two_rounds():
    w = _crowded_elderly_workspace()
    calls = []
    seen = []

    async def regenerate(workspace):
        calls.append(1)
        seen.append(list(workspace.get("_constraint_refinement", [])))
        return [_row("p1"), _row("p2"), _row("p3")]  # still crowded

    report, rounds = asyncio.run(reflect.review_and_refine(w, regenerate))
    assert rounds == 2
    assert len(calls) == 2
    # round numbering handed to the model: 1 then 1,2
    assert [e["round"] for e in seen[0]] == [1]
    assert [e["round"] for e in seen[1]] == [1, 2]
    # the loop stopped while still violating -- it reports, it does not loop forever
    densities = [f for f in report if f["constraint"] == "poi_density"]
    assert len(densities) == 1
    assert densities[0]["status"] == "warn"
    assert reflect.needs_refine(report) is True
    assert "_constraint_refinement" not in w


def test_review_and_refine_max_rounds_zero_only_examines():
    w = _crowded_elderly_workspace()
    calls = []

    async def regenerate(workspace):
        calls.append(1)
        return [_row("p1")]

    report, rounds = asyncio.run(reflect.review_and_refine(w, regenerate, max_rounds=0))
    assert rounds == 0
    assert calls == []
    # examine-only: the violation is surfaced but left unfixed
    assert reflect.needs_refine(report) is True


# ---------------------------------------------------------------------------
# review_and_refine: regenerate raises
# ---------------------------------------------------------------------------

def test_review_and_refine_regenerate_error_keeps_rounds_at_zero():
    # rounds += 1 sits outside the try (reflect.py:102), so a raising
    # regenerate hits the break at reflect.py:101 before the increment.
    # Real behaviour, not a bug: the caller gets the round-0 report back with
    # rounds == 0 and can tell that no refinement actually happened.
    w = _crowded_elderly_workspace()
    calls = []

    async def regenerate(workspace):
        calls.append(1)
        raise RuntimeError("model unavailable")

    report, rounds = asyncio.run(reflect.review_and_refine(w, regenerate))
    assert rounds == 0
    assert len(calls) == 1
    assert reflect.needs_refine(report) is True
    assert "_constraint_refinement" not in w
