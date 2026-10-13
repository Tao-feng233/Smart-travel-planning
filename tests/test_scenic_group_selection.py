"""Selecting a scenic scope expands real children and keeps their trip coherent."""

import asyncio
import copy
import json

import pytest

from app.agents import edit_tools
from app.core.errors import DataError
from app.planning import visit_analysis
from app.travel import actions, selections, spot_hierarchy
from app.travel.handlers.places import do_select


def trip():
    rows = [
        {"id": "sea", "name": "海滨风景区"},
        {"id": "pier", "name": "栈桥", "parent_id": "sea"},
        {"id": "park", "name": "海边公园", "parent_id": "sea"},
        {"id": "beach", "name": "海滩", "parent_id": "sea"},
        {"id": "other", "name": "独立博物馆"},
    ]
    return {
        "requirements": {"city": "青岛", "start_date": "2026-10-12", "days": 2},
        "catalog": {
            p["id"]: {**p, "kind": "spot", "location": "120.3,36.06"} for p in rows
        },
        "selected_spots": [],
        "spot_search": {"ids": [p["id"] for p in rows]},
    }


async def handler(w, action, args, progress):
    return await do_select(w, action, args, progress, None)


def select(w, cid, **args):
    return asyncio.run(handler(w, "select", {"id": cid, **args}, lambda _: None))


def test_parent_selects_children_and_toggle_removes_only_its_scope():
    w = trip()
    select(w, "other")
    answer = select(w, "sea")
    assert w["selected_spots"] == ["other", "pier", "park", "beach"]
    assert "3" in answer and "内部" in answer
    assert spot_hierarchy.state(w)["parent_coverage"] == {
        "sea": ["pier", "park", "beach"]
    }
    w["visit_requests"] = {"pier": {"date": "2026-10-12"}}
    w["visit_order"] = ["pier", "other"]
    select(w, "sea")
    assert w["selected_spots"] == ["other"]
    assert w["visit_requests"] == {} and w["visit_order"] == ["other"]


def test_partial_parent_selection_fills_missing_children_and_model_is_idempotent():
    w = trip()
    select(w, "pier")
    select(w, "sea")
    assert set(w["selected_spots"]) == {"pier", "park", "beach"}
    w["spots_confirmed"] = True
    w["plan"] = {"stale": False}
    before = copy.deepcopy(w)
    for _ in range(2):
        asyncio.run(edit_tools.select(w, "sea", {}, handler, lambda _: None))
        asyncio.run(
            actions.apply_choices(w, {"select_ids": ["sea"]}, lambda _: None, handler)
        )
    assert w == before
    assert selections.remove_selection(w, "sea")
    assert w["selected_spots"] == []


def test_nested_scope_uses_leaves_not_containers_and_keeps_parent_pin():
    w = trip()
    w["catalog"]["house"] = {
        "id": "house",
        "name": "花石楼",
        "kind": "spot",
        "parent_id": "park",
    }
    w["spot_search"]["ids"].append("house")
    w["visit_requests"] = {"sea": {"date": "2026-10-13", "period": "afternoon"}}
    select(w, "sea")
    assert set(w["selected_spots"]) == {"pier", "house", "beach"}
    state = spot_hierarchy.state(w)
    assert all(
        state["visit_requests"][cid]["date"] == "2026-10-13"
        for cid in state["active_ids"]
    )


def test_unverified_names_hidden_stale_and_rejected_children_are_not_auto_selected():
    w = trip()
    w["catalog"]["other"]["name"] = "海滨风景区·未知地点"
    w["catalog"]["park"]["stale"] = True
    w["rejected_spots"] = ["beach"]
    w["catalog"]["hidden"] = {"id": "hidden", "kind": "spot", "parent_id": "sea"}
    select(w, "sea")
    assert w["selected_spots"] == ["pier"]


def test_group_limit_failure_leaves_selection_untouched():
    w = trip()
    w["selected_spots"] = ["old" + str(n) for n in range(119)]
    before = copy.deepcopy(w)
    with pytest.raises(DataError):
        select(w, "sea")
    assert w == before


def test_fitting_siblings_stay_together_and_fixed_dates_or_capacity_can_split():
    w = trip()
    w["selected_spots"] = ["pier", "park", "beach", "other"]
    estimates = {cid: {"duration": 60} for cid in w["selected_spots"]}
    rows = visit_analysis.allocate(w, estimates)
    assert len({i["date"] for i in rows if i["candidate_id"] != "other"}) == 1
    w["visit_requests"] = {
        "pier": {"date": "2026-10-12"},
        "beach": {"date": "2026-10-13"},
    }
    rows = visit_analysis.allocate(w, estimates)
    assert {i["candidate_id"]: i["date"] for i in rows}["beach"] == "2026-10-13"
    assert {i["candidate_id"]: i["date"] for i in rows}["pier"] == "2026-10-12"
    w.pop("visit_requests")
    rows = visit_analysis.allocate(
        w, {cid: {"duration": 360} for cid in w["selected_spots"]}
    )
    assert len({i["date"] for i in rows if i["candidate_id"] != "other"}) == 2


def test_model_analysis_reconsiders_avoidable_split_and_fallback_keeps_group():
    w = trip()
    select(w, "sea")
    calls = []

    async def model(messages, **kwargs):
        calls.append(copy.deepcopy(messages))
        return {
            "content": json.dumps(
                {
                    "items": [
                        {
                            "candidate_id": cid,
                            "date": "2026-10-12" if cid == "pier" else "2026-10-13",
                            "duration": 60,
                            "period": "any",
                            "reason": "合成分配",
                        }
                        for cid in w["selected_spots"]
                    ]
                }
            )
        }, {}

    result = asyncio.run(visit_analysis.analyze(w, model, lambda _: None))
    assert len(calls) == 2
    payload = json.loads(calls[0][1]["content"])
    assert payload["scenic_groups"][0]["candidate_ids"] == ["pier", "park", "beach"]
    assert "同一天" in calls[0][0]["content"]
    assert "内部地点分散" in calls[1][-1]["content"]
    assert len({i["date"] for i in result["items"]}) == 1
    assert all(i["duration"] == 60 for i in result["items"])
    assert not any(
        i["code"] == "unbalanced_estimate"
        for i in visit_analysis.distribution_warnings(w, result["items"])
    )


def test_final_proposal_requests_same_day_and_keeps_siblings_adjacent(tmp_path):
    from app.planning import proposals

    w = trip()
    select(w, "sea")
    select(w, "other")
    calls = []

    async def model(messages, **kwargs):
        calls.append(copy.deepcopy(messages))
        # First draft unnecessarily splits siblings. The revised draft is coherent,
        # but interleaves an unrelated stop inside the scenic scope.
        days = (
            [
                {
                    "date": "2026-10-12",
                    "items": [{"candidate_id": "pier", "duration": 60}],
                },
                {
                    "date": "2026-10-13",
                    "items": [
                        {"candidate_id": cid, "duration": 60}
                        for cid in ("park", "beach", "other")
                    ],
                },
            ]
            if len(calls) == 1
            else [
                {
                    "date": "2026-10-12",
                    "items": [
                        {"candidate_id": cid, "duration": 60}
                        for cid in ("pier", "other", "park", "beach")
                    ],
                }
            ]
        )
        return {"content": json.dumps({"days": days})}, {}

    dates = ["2026-10-12", "2026-10-13"]
    _, days, _ = asyncio.run(
        proposals.create(
            w,
            visit_analysis.selected(w),
            {"dates": dates, "tour_dates": dates},
            "合成提示词",
            lambda _: None,
            model,
            tmp_path,
        )
    )
    assert len(calls) == 2
    assert "scenic_group_split" in calls[1][-1]["content"]
    assert [i["candidate_id"] for i in days[0]["items"]] == [
        "pier",
        "park",
        "beach",
        "other",
    ]


def test_expanding_old_parent_selection_replaces_intermediate_containers():
    w = trip()
    w["catalog"]["house"] = {
        "id": "house",
        "name": "花石楼",
        "kind": "spot",
        "parent_id": "park",
    }
    w["spot_search"]["ids"].append("house")
    w["selected_spots"] = ["sea", "park"]
    asyncio.run(edit_tools.select(w, "sea", {}, handler, lambda _: None))
    assert set(w["selected_spots"]) == {"pier", "house", "beach"}


def test_siblings_do_not_reorder_explicit_sequence():
    from app.planning.scenic_grouping import ordered

    w = trip()
    w["selected_spots"] = ["pier", "park", "beach", "other"]
    w["visit_order"] = ["pier", "other", "park", "beach"]
    items = [{"candidate_id": cid, "period": "any"} for cid in w["visit_order"]]
    assert ordered(w, items) == items


def test_small_scope_is_not_split_by_model_batch_boundary():
    from app.planning.scenic_grouping import batches

    w = trip()
    others = [
        {"id": "single" + str(n), "name": "独立地点", "kind": "spot"} for n in range(15)
    ]
    w["catalog"].update({p["id"]: p for p in others})
    spots = others + [w["catalog"][cid] for cid in ("pier", "park", "beach")]
    w["selected_spots"] = [p["id"] for p in spots]
    chunks = batches(w, spots)
    assert [len(chunk) for chunk in chunks] == [15, 3]
    assert {p["id"] for p in chunks[1]} == {"pier", "park", "beach"}


def test_generated_plan_has_children_once_and_no_parent_visit(monkeypatch, tmp_path):
    from app.planning import engine

    w = trip()
    select(w, "sea")
    w.update(messages=[], tickets={})
    payloads = []

    async def model(messages, **kwargs):
        payloads.append(json.loads(messages[1]["content"]))
        value = (
            {"issues": [], "summary": "合成审核"}
            if kwargs.get("label") == "review"
            else {
                "days": [
                    {
                        "date": "2026-10-12",
                        "items": [
                            {"candidate_id": cid, "duration": 45}
                            for cid in ("pier", "park", "beach")
                        ],
                    }
                ]
            }
        )
        return {"content": json.dumps(value)}, {}

    async def tool(*args):
        return {"items": []}

    monkeypatch.setattr(engine, "llm", model)
    monkeypatch.setattr(engine, "local_tool", tool)
    monkeypatch.setattr(engine, "RUNTIME", tmp_path)
    plan = asyncio.run(engine.generate(w, lambda _: None))
    events = [
        (day["date"], e["candidate_id"])
        for day in plan["days"]
        for e in day["events"]
        if e["kind"] == "spot"
    ]
    assert events == [("2026-10-12", cid) for cid in ("pier", "park", "beach")]
    assert payloads[0]["scenic_groups"][0]["candidate_ids"] == ["pier", "park", "beach"]
    assert plan["parent_coverage"] == {"sea": ["pier", "park", "beach"]}
