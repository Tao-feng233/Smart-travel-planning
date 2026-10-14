"""Lightweight reflect loop over the people-dimension constraint report.

The existing ``visit_analysis.analyze`` already reflects on *minute capacity*
(distribution_warnings). This module reflects on the *people dimension*
(``constraint_engine.examine``): after a plan is generated, run the
examination, and when violations are found, hand the violations back to the
model so it can refine the visit suggestions. Caps at 2 rounds to avoid
infinite loops.

Academic anchor: DeepTravel (arxiv 2509.21842) -- "reflect on tool responses
to explore, verify, and refine". The "tool response" here is the constraint
report; refinement is the regenerated visit suggestion.

The module is deliberately NOT wired into the main pipeline. It exports pure
helpers so the team can choose where to mount the loop (preview, final plan,
or a new endpoint) without touching the existing generator. Nothing here
mutates the workspace; regeneration is delegated to a caller-supplied
callable.
"""

import json

from app.planning import constraint_engine


def findings(w, rows=None):
    """Return the people-dimension examination report for the current plan."""
    return constraint_engine.examine(w, rows)


def needs_refine(report):
    """True when the report contains at least one warn-level finding."""
    return any(f.get("status") == "warn" for f in report)


def build_prompt(report):
    """Turn a constraint report into a JSON refinement prompt for the LLM.

    Returns a user-message string. The model is expected to regenerate its
    visit_suggestion items avoiding the listed violations. When the report is
    clean, returns None (no refinement needed).
    """
    violations = [f for f in report if f.get("status") == "warn"]
    if not violations:
        return None
    payload = {
        "refinement_request": "以下人员维度约束被违反,请重新生成 visit_suggestion 避免这些问题,保持景点 id 不变,仅调整 date/period/duration。",
        "violations": [
            {
                "constraint": v.get("constraint"),
                "date": v.get("date"),
                "message": v.get("message"),
                "related_rows": v.get("related_rows"),
                "profile": v.get("profile"),
            }
            for v in violations
        ],
        "max_rounds": 2,
        "hint": {
            "poi_density": "减少该半天的 POI 数量,把多余的移到其他日期或时段。",
            "walking_steps": "缩短相邻 POI 间的绕行,或拆段加酒店午休。",
            "midday_rest_missing": "在 13:00-15:00 之间插入一个 rest_type=midday 的休息。",
            "opening_hours": "把到达时间移到营业时段内。",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def review_and_refine(w, regenerate, *, max_rounds=2):
    """Run examine -> refine loop, returning the final report.

    Args:
        w: workspace dict.
        regenerate: async callable(w) -> rows. Called to regenerate the visit
            analysis items after feeding the violation prompt back. The
            caller controls how (e.g. re-invoke visit_analysis.analyze).
        max_rounds: cap on refinement iterations. 0 means examine-only.

    Returns:
        (report, rounds_used) where report is the final constraint_engine
        findings list and rounds_used is the number of regeneration calls made.

    The function does NOT wire itself into visit_analysis.analyze. The caller
    is responsible for passing a regenerate that actually feeds the refinement
    prompt to the model (see build_prompt).
    """
    rounds = 0
    report = findings(w)
    while rounds < max_rounds and needs_refine(report):
        prompt = build_prompt(report)
        if prompt is None:
            break
        # Hand the prompt to the workspace so the caller's regenerate can pick
        # it up; this keeps the loop decoupled from any specific LLM client.
        w.setdefault("_constraint_refinement", []).append(
            {"round": rounds + 1, "prompt": prompt}
        )
        try:
            rows = await regenerate(w)
        except Exception:
            break
        rounds += 1
        report = findings(w, rows)
    # Clean up the scratch field so we do not leak state into the workspace.
    w.pop("_constraint_refinement", None)
    return report, rounds
