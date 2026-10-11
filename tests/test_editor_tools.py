"""Regression scenarios for authorized edits, real observations and failed commits."""

import asyncio
import copy
import json

import pytest

from app.agents import planner, goals, edit_tools, auto_selection, replies
from app.core.errors import DataError
from app.travel import actions, stay_plan
from app.travel.selections import remove_selection


def workspace(mode="act", scopes=None, generate=False):
    value = {
        "id": "edit-test",
        "revision": 3,
        "title": "测试",
        "requirements": {
            "city": "青岛",
            "start_date": "2026-10-12",
            "days": 2,
            "adults": 2,
            "intercity_mode": "self_arranged",
        },
        "catalog": {
            "s1": {"id": "s1", "kind": "spot", "name": "栈桥"},
            "s2": {"id": "s2", "kind": "spot", "name": "八大关"},
        },
        "selected_spots": ["s1"],
        "messages": [],
        "meal_choices": {},
        "visit_requests": {},
        "tickets": {},
        "last_question": "替换景点，晚上九点结束，之前的海滨偏好不要了",
    }
    goals.start(
        value,
        {
            "mission": {
                "mode": mode,
                "objective": "按要求修改旅行",
                "scopes": scopes or [],
                "multi_step": True,
                "generate_plan": generate,
            }
        },
    )
    return value


def call(name, args):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }, {}


async def select_handler(w, action, args, progress):
    if action == "select":
        cid = args["id"]
        if w["catalog"][cid]["kind"] == "spot":
            w["selected_spots"].append(cid)
        elif w["catalog"][cid]["kind"] == "hotel":
            stay_plan.assign(w, cid, args.get("stay_dates") or [args["stay_date"]])
            w["hotel"] = w["catalog"][cid]
        if w.get("plan"):
            w["plan"]["stale"] = True
        return "选择已更新"
    raise AssertionError(action)


@pytest.mark.parametrize("mode", ["query", "consult", "explain"])
def test_read_only_goals_do_not_expose_or_execute_selection(mode):
    w = workspace(mode)
    names = {entry["function"]["name"] for entry in goals.tools(w["assistant_goal"])}
    assert "get_travel_state" in names and "replace_candidate" not in names
    with pytest.raises(DataError, match="未授权"):
        asyncio.run(
            edit_tools.execute(
                w, "select_candidate", {"id": "s2"}, select_handler, lambda _: None
            )
        )
    assert w["selected_spots"] == ["s1"]


def test_replacement_failure_rolls_back_the_removal_and_old_plan():
    w = workspace()
    w["plan"] = {"title": "原版", "days": [], "stale": False}
    w["visit_requests"] = {"s1": {"date": "2026-10-12"}}
    before = copy.deepcopy(w)

    async def failed(draft, action, args, progress):
        draft["selected_spots"].append(args["id"])
        draft["plan"]["title"] = "未完成版"
        raise DataError("路线暂时不可用")

    with pytest.raises(DataError, match="路线"):
        asyncio.run(
            edit_tools.execute(
                w,
                "replace_candidate",
                {"old_id": "s1", "new_id": "s2"},
                failed,
                lambda _: None,
            )
        )
    assert w == before


def test_selection_is_idempotent_and_successful_replacement_clears_old_pins():
    w = workspace()
    w["visit_requests"] = {"s1": {"date": "2026-10-12"}}
    w["visit_order"] = ["s1"]
    asyncio.run(
        edit_tools.execute(
            w, "select_candidate", {"id": "s1"}, select_handler, lambda _: None
        )
    )
    assert w["selected_spots"] == ["s1"]
    asyncio.run(
        edit_tools.execute(
            w,
            "replace_candidate",
            {"old_id": "s1", "new_id": "s2"},
            select_handler,
            lambda _: None,
        )
    )
    assert (
        w["selected_spots"] == ["s2"]
        and w["visit_requests"] == {}
        and w["visit_order"] == []
    )


def test_hotel_replacement_changes_only_the_requested_night():
    w = workspace(scopes=["hotel"])
    w["catalog"].update(
        {cid: {"id": cid, "kind": "hotel", "name": cid} for cid in ("h1", "h2")}
    )
    w["stay_hotels"] = {"2026-10-12": "h1", "2026-10-13": "h1"}
    w["hotel"] = w["catalog"]["h1"]
    asyncio.run(
        edit_tools.execute(
            w,
            "replace_candidate",
            {"old_id": "h1", "new_id": "h2", "stay_date": "2026-10-12"},
            select_handler,
            lambda _: None,
        )
    )
    assert w["stay_hotels"] == {"2026-10-12": "h2", "2026-10-13": "h1"}


def test_removing_a_restaurant_removes_its_meals_but_preserves_other_meals():
    w = workspace()
    w["meal_choices"] = {
        "2026-10-12|lunch": {"food_id": "f1"},
        "2026-10-12|dinner": {"food_id": "f2"},
    }
    assert remove_selection(w, "f1")
    assert w["meal_choices"] == {"2026-10-12|dinner": {"food_id": "f2"}}


def test_scope_and_ticket_authority_are_enforced_even_for_hallucinated_calls():
    w = workspace("delegate", ["food"])
    w["catalog"]["ticket"] = {"id": "ticket", "kind": "train", "name": "G123"}
    for cid in ("s2", "ticket"):
        with pytest.raises(DataError):
            asyncio.run(
                edit_tools.execute(
                    w, "select_candidate", {"id": cid}, select_handler, lambda _: None
                )
            )
    assert w["selected_spots"] == ["s1"]


def test_replacing_outbound_does_not_grant_authority_over_return():
    w = workspace()
    w["catalog"].update(
        {
            cid: {"id": cid, "kind": "train", "name": cid, "direction": direction}
            for cid, direction in [
                ("old-out", "outbound"),
                ("new-out", "outbound"),
                ("return", "return"),
            ]
        }
    )
    w["selected_transport"] = w["catalog"]["old-out"]
    w["selected_return"] = w["catalog"]["return"]
    goals.start(
        w,
        {
            "select_ids": ["new-out"],
            "replace": True,
            "mission": {
                "mode": "act",
                "objective": "只换去程",
                "scopes": [],
                "multi_step": True,
            },
        },
    )
    assert set(w["assistant_goal"]["transport_ids"]) == {"new-out", "old-out"}
    with pytest.raises(DataError, match="交通"):
        asyncio.run(
            edit_tools.execute(
                w, "remove_candidate", {"id": "return"}, select_handler, lambda _: None
            )
        )


def test_formal_condition_edits_need_user_evidence_and_replace_preferences():
    w = workspace()
    w["requirements"]["preferences"] = ["海滨", "人文"]
    before = copy.deepcopy(w)
    with pytest.raises(DataError, match="原文"):
        asyncio.run(
            edit_tools.execute(
                w,
                "update_requirements",
                {"patch": {"days": 4}},
                select_handler,
                lambda _: None,
            )
        )
    assert w == before
    asyncio.run(
        edit_tools.execute(
            w,
            "update_requirements",
            {
                "patch": {"day_end": "21:00"},
                "evidence": {"day_end": "晚上九点结束"},
                "preference_updates": {
                    "preferences": {"mode": "remove", "values": ["海滨"]}
                },
            },
            select_handler,
            lambda _: None,
        )
    )
    assert w["requirements"]["day_end"] == "21:00" and w["requirements"][
        "preferences"
    ] == ["人文"]


def test_initial_mixed_selection_failure_is_atomic():
    w = workspace()
    before = copy.deepcopy(w)
    with pytest.raises(DataError):
        asyncio.run(
            actions.apply_choices(
                w,
                {"remove_ids": ["s1"], "select_ids": ["s2", "missing"]},
                lambda _: None,
                select_handler,
            )
        )
    assert w == before


def test_act_goal_continues_from_query_to_selection_to_plan(monkeypatch):
    w = workspace()
    w.pop("assistant_goal")
    w["selected_spots"] = []
    seen = []
    decisions = [
        (
            "submit_intent",
            {
                "action": "search_spots",
                "patch": {},
                "preference_mode": "default",
                "mission": {
                    "mode": "act",
                    "objective": "查询并选景点后生成计划",
                    "scopes": ["spots"],
                    "multi_step": True,
                    "generate_plan": True,
                },
            },
        ),
        ("select_candidate", {"id": "s2"}),
        ("generate_plan", {}),
        (
            "finish_request",
            {"status": "completed", "answer": "已选择八大关并生成计划书。"},
        ),
    ]

    async def model(messages, **kwargs):
        if len(seen) >= 1:
            assert any(m.get("role") == "tool" for m in messages)
        return call(*decisions.pop(0))

    async def handler(draft, action, args, progress):
        seen.append(action)
        if action == "search_spots":
            draft["spot_search"] = {"ids": ["s2"]}
        elif action == "select":
            draft["selected_spots"].append(args["id"])
        elif action == "plan":
            assert draft["selected_spots"] == ["s2"]
            draft["plan"] = {"title": "已生成", "days": [], "stale": False}
        return action + "成功"

    monkeypatch.setattr(planner, "llm", model)
    monkeypatch.setattr(planner, "handle", handler)
    token = replies.SINK.set(None)
    try:
        answer = asyncio.run(
            planner.run_chat(w, "帮我查景点并选好后生成计划", lambda _: None)
        )
    finally:
        replies.SINK.reset(token)
    assert seen == ["search_spots", "select", "plan"]
    assert (
        w["assistant_goal"]["status"] == "completed" and w["plan"]["title"] == "已生成"
    )
    assert w["last_action"] == "plan" and "生成" in answer


def test_failed_first_generation_can_query_and_select_before_retry(monkeypatch):
    w = workspace("edit_plan", generate=True)
    w["selected_spots"] = []
    first = goals.observation(w, "plan", {}, "", DataError("请先选择想去的景点"))
    decisions = [
        ("select_candidate", {"id": "s2"}),
        ("generate_plan", {}),
        ("finish_request", {"status": "completed", "answer": "已生成"}),
    ]

    async def model(*args, **kwargs):
        return call(*decisions.pop(0))

    async def handler(draft, action, args, progress):
        if action == "select":
            draft["selected_spots"].append(args["id"])
        if action == "plan":
            draft["plan"] = {"title": "成功", "days": [], "stale": False}
        return "成功"

    asyncio.run(goals.continue_goal(w, first, model, handler, lambda _: None))
    assert w["assistant_goal"]["status"] == "completed" and w["selected_spots"] == [
        "s2"
    ]


def test_finish_cannot_claim_a_requested_plan_that_was_not_generated():
    w = workspace(generate=True)
    first = goals.observation(w, "search_spots", {}, "已查候选")

    async def model(*args, **kwargs):
        return call("finish_request", {"status": "completed", "answer": "完成了"})

    result = asyncio.run(
        goals.continue_goal(w, first, model, select_handler, lambda _: None)
    )
    assert w["assistant_goal"]["status"] == "partial" and "尚未完成" in result


def test_partial_delegation_can_continue_but_complete_delegation_avoids_an_extra_model_round():
    w = workspace("delegate", ["hotel"])
    w["auto_selection_result"] = {"errors": [{"scope": "hotel", "message": "未查到"}]}
    assert goals.continue_needed(w, w["assistant_goal"], "arrange_remaining")
    w["auto_selection_result"]["errors"] = []
    assert not goals.continue_needed(w, w["assistant_goal"], "arrange_remaining")


def test_finish_cannot_claim_completion_with_unresolved_delegated_lodging():
    from app.agents.execution import validate_finish

    w = workspace("delegate", ["hotel"])
    w["auto_selection_result"] = {"errors": [{"scope": "hotel", "message": "未查到"}]}
    goals.observation(w, "arrange_remaining", {}, "住宿尚未完成")
    with pytest.raises(DataError, match="住宿"):
        validate_finish(w, "completed")


def test_cancelling_current_edit_preserves_a_previous_committed_step():
    w = workspace()
    asyncio.run(
        edit_tools.execute(
            w, "select_candidate", {"id": "s2"}, select_handler, lambda _: None
        )
    )
    before = copy.deepcopy(w)

    async def cancelled(draft, action, args, progress):
        draft["selected_spots"].clear()
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(actions.run(w, "plan", {}, lambda _: None, cancelled))
    assert w == before


def test_query_preview_is_local_to_the_task_and_does_not_expose_partial_choices():
    w = workspace()

    async def handler(draft, action, args, progress):
        draft["catalog"]["new"] = {"id": "new", "kind": "spot", "name": "已查询候选"}
        draft["spot_search"] = {"ids": ["new"]}
        draft["selected_spots"] = []
        preview = actions.QUERY_PREVIEW.get()
        assert preview["spot_search"]["ids"] == ["new"]
        assert w["selected_spots"] == ["s1"] and "new" not in w["catalog"]
        raise DataError("查询没有完成")

    with pytest.raises(DataError):
        asyncio.run(actions.run(w, "search_spots", {}, lambda _: None, handler))
    assert (
        actions.QUERY_PREVIEW.get() is None
        and w["selected_spots"] == ["s1"]
        and "new" not in w["catalog"]
    )


def test_delegate_with_known_conditions_does_not_force_another_confirmation():
    w = workspace("delegate", ["spots"])
    intent = {
        "action": "plan",
        "patch": {},
        "mission": {
            "mode": "delegate",
            "objective": "补齐景点",
            "scopes": ["spots"],
            "multi_step": True,
            "generate_plan": False,
        },
    }
    normalized = auto_selection.delegation(w, "剩下的景点帮我安排", intent)
    assert normalized["action"] == "arrange_remaining"


def test_remaining_spots_are_supplemented_without_erasing_existing_choices(monkeypatch):
    w = workspace("delegate", ["spots"])
    w["catalog"]["s3"] = {"id": "s3", "kind": "spot", "name": "五四广场"}

    async def handler(draft, action, args, progress):
        assert action == "search_spots"
        draft["spot_search"] = {"ids": ["s1", "s2", "s3"]}
        return "候选已取得"

    async def choose(draft, pool, *args, **kwargs):
        assert [p["id"] for p in pool] == ["s2", "s3"]
        return ["s2", "s3"], "按行程补齐"

    from app.planning import visit_analysis

    async def analysis(*args, **kwargs):
        return None

    monkeypatch.setattr(auto_selection, "choose", choose)
    monkeypatch.setattr(visit_analysis, "analyze", analysis)
    asyncio.run(
        auto_selection.arrange(
            w, {"auto_categories": ["spots"]}, lambda _: None, None, handler
        )
    )
    assert w["selected_spots"] == ["s1", "s2", "s3"]


def test_one_day_delegation_can_select_the_touring_night_hotel(monkeypatch):
    w = workspace("delegate", ["hotel"])
    w["requirements"]["days"] = 1
    w["catalog"]["h"] = {
        "id": "h",
        "kind": "hotel",
        "name": "测试酒店",
        "location": "120.32,36.07",
    }
    queried = []

    async def handler(draft, action, args, progress):
        queried.append(action)
        if action == "search_hotels":
            draft["stay_plan"] = {
                "rows": [{"date": "2026-10-12", "candidate_ids": ["h"]}]
            }
        elif action == "select":
            stay_plan.assign(draft, "h", [args["stay_date"]])
            draft["hotel"] = draft["catalog"]["h"]
        return "成功"

    async def choose(*args, **kwargs):
        return ["h"], "位置合适"

    monkeypatch.setattr(auto_selection, "choose", choose)
    asyncio.run(
        auto_selection.arrange(
            w, {"auto_categories": ["hotel"]}, lambda _: None, None, handler
        )
    )
    assert (
        queried == ["search_hotels", "select"] and w["stay_hotels"]["2026-10-12"] == "h"
    )


def test_query_request_cannot_clear_preferences_or_change_an_existing_pace():
    w = workspace("query")
    w["requirements"]["pace"] = "relaxed"
    intent = {
        "action": "chat",
        "patch": {"pace": "packed"},
        "preference_updates": {"preferences": {"mode": "replace", "values": []}},
        "mission": {
            "mode": "query",
            "objective": "比较紧凑与休闲安排",
            "multi_step": False,
        },
    }
    value = goals.normalize(w, "只比较一下", intent)
    assert value["patch"] == {} and "preference_updates" not in value
