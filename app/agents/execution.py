"""Bounded model decisions over factual observations and authorized edits."""

import hashlib
import json
import time

from app import prompts
from app.agents import edit_tools
from app.core.errors import DataError
from app.integrations.enrichment import model_facts
from app.travel import actions

MAX_STEPS = 10


def fingerprint(workspace):
    keys = (
        "requirements",
        "catalog",
        "selected_spots",
        "hotel",
        "stay_hotels",
        "selected_rooms",
        "selected_transport",
        "selected_return",
        "meal_choices",
        "meal_mode",
        "visit_requests",
        "visit_order",
        "plan",
        "timeline_adjustment",
        "weather",
        "spot_search",
        "hotel_query",
        "food_query",
    )
    content = json.dumps(
        {key: workspace.get(key) for key in keys}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(content.encode()).hexdigest()


def validate_finish(workspace, status):
    goal = workspace["assistant_goal"]
    if status != "completed":
        return
    if workspace.get("pending_auto_selection") or workspace.get("pending_plan_warning"):
        raise DataError("仍有待用户确认的条件，不能声称已经完成。")
    if workspace.get("auto_selection_run"):
        raise DataError("仍有尚未执行的代选批次，请继续或说明部分完成。")
    arranged = any(
        row["tool"] in ("arrange_remaining", "continue_arrangement")
        for row in goal["observations"]
    )
    if arranged:
        from app.travel.stay_plan import unassigned
        from app.planning.schedule import build

        meal_keys = {
            row["date"] + "|" + row["period"]
            for row in build(workspace)["meal_slots"]
            if not row.get("included_in_room")
        }
        for error in (workspace.get("auto_selection_result") or {}).get("errors", []):
            scope = error.get("scope")
            if (
                scope == "hotel"
                and unassigned(workspace)
                and not workspace.get("stay_skipped")
            ):
                raise DataError("仍有住宿夜晚没有安排，请继续或说明部分完成。")
            key = str(error.get("date")) + "|" + str(error.get("period"))
            if (
                scope == "food"
                and key in meal_keys
                and key not in workspace.get("meal_choices", {})
                and workspace.get("meal_mode") != "self"
            ):
                raise DataError("仍有餐次没有安排，请继续或说明部分完成。")
    if goal.get("generate_plan"):
        plan = workspace.get("plan")
        generated = any(
            row["ok"]
            and row["tool"]
            in (
                "plan",
                "optimize_plan",
                "generate_plan",
                "arrange_remaining",
                "continue_arrangement",
            )
            for row in goal["observations"]
        )
        if not plan or plan.get("stale") or not generated:
            raise DataError("用户要求的计划书尚未成功生成，不能标记完成。")


async def continue_goal(workspace, first, model, handler, progress):
    from app.agents import goals

    goal = workspace["assistant_goal"]
    messages = [
        {"role": "system", "content": prompts.system("goal")},
        {
            "role": "user",
            "content": json.dumps(
                model_facts(
                    {
                        "goal": goal,
                        "user_request": workspace.get("last_question"),
                        "requirements": workspace["requirements"],
                        "plan": goals.plan_context(workspace),
                        "interaction_state": prompts.interaction_state(workspace),
                        "editing_authorized": edit_tools.editable(goal),
                    }
                ),
                ensure_ascii=False,
            ),
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "initial",
                    "type": "function",
                    "function": {
                        "name": first["tool"],
                        "arguments": json.dumps(first["arguments"], ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "initial",
            "content": json.dumps(first, ensure_ascii=False),
        },
    ]
    initial = {
        key: value
        for key, value in first["arguments"].items()
        if key in goals.READ_TOOLS.get(first["tool"], ("", {}))[1]
        and value not in (None, "", [])
    }
    used = {
        (first["tool"], json.dumps(initial, sort_keys=True), fingerprint(workspace))
    }
    invalid = 0
    for step in range(MAX_STEPS):
        progress(
            "正在根据实际结果继续安排"
            if edit_tools.editable(goal)
            else "正在根据查询结果判断还需要哪些信息"
        )
        context = model_facts(
            {
                "catalog": list(workspace.get("catalog", {}).values())[-30:],
                "selected_spots": workspace.get("selected_spots", []),
                "stay_hotels": workspace.get("stay_hotels", {}),
                "meal_choices": workspace.get("meal_choices", {}),
                "food_query": workspace.get("food_query"),
                "hotel_query": workspace.get("hotel_query"),
                "weather": workspace.get("weather"),
                "plan": goals.plan_context(workspace),
                "unfinished_arrangement": bool(workspace.get("auto_selection_run")),
            }
        )
        message, _ = await model(
            messages
            + [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            tools=goals.tools(goal),
            max_tokens=1800,
            label="goal_decide",
        )
        calls = message.get("tool_calls") or []
        if len(calls) != 1 or not isinstance(calls[0].get("function"), dict):
            invalid += 1
            messages.append(
                {
                    "role": "user",
                    "content": "请每次调用一项可用工具，或用finish_request说明实际结果。",
                }
            )
            if invalid >= 2:
                break
            continue
        call = calls[0]
        # Some compatible endpoints omit IDs; normalize both halves of the exchange.
        call["id"] = call.get("id") or "step-" + str(step)
        call["type"] = "function"
        message["role"] = "assistant"
        messages.append(message)
        name = call["function"].get("name")
        started = time.monotonic()
        arguments = {}
        try:

            def invalid_number(value):
                raise ValueError("工具不能使用非有限数值。")

            arguments = json.loads(
                call["function"].get("arguments", ""), parse_constant=invalid_number
            )
            if not isinstance(arguments, dict):
                raise DataError("工具参数必须为对象。")
            if name == "finish_request":
                if (
                    arguments.get("status")
                    not in ("completed", "needs_info", "partial")
                    or not isinstance(arguments.get("answer"), str)
                    or not arguments["answer"].strip()
                    or set(arguments) - {"status", "answer"}
                ):
                    raise DataError("结束状态或答复无效。")
                validate_finish(workspace, arguments["status"])
                goal["status"] = arguments["status"]
                return arguments["answer"][:3500]
            if name == "request_auto_selection":
                spec = next(
                    item["function"]["parameters"]
                    for item in goals.tools(goal)
                    if item["function"]["name"] == name
                )
                edit_tools.validate((None, spec["properties"], []), arguments)
                answer = await actions.run(
                    workspace,
                    name,
                    {**arguments, "allow_missing": True},
                    progress,
                    handler,
                )
                goals.observation(
                    workspace,
                    name,
                    arguments,
                    answer,
                    elapsed=time.monotonic() - started,
                )
                goal["status"] = "awaiting_confirmation"
                return answer
            editing = edit_tools.specifications(goal)
            if name not in goals.READ_TOOLS and name not in editing:
                raise DataError("该工具不在本轮已授权能力范围。")
            if name in goals.READ_TOOLS:
                edit_tools.validate((None, goals.READ_TOOLS[name][1], []), arguments)
            identity = (
                name,
                json.dumps(
                    {
                        key: value
                        for key, value in arguments.items()
                        if value not in (None, "", [])
                    },
                    sort_keys=True,
                ),
                fingerprint(workspace),
            )
            if identity in used:
                raise DataError("相同状态下该操作已执行，请使用已有结果或继续下一步。")
            used.add(identity)
            if name in editing:
                answer = await edit_tools.execute(
                    workspace, name, arguments, handler, progress
                )
            else:
                answer = await actions.run(
                    workspace, name, arguments, progress, handler
                )
            row = goals.observation(
                workspace, name, arguments, answer, elapsed=time.monotonic() - started
            )
            if name != "get_travel_state":
                workspace["turn_action"] = {
                    "select_candidate": "select",
                    "replace_candidate": "select",
                    "remove_candidate": "select",
                    "generate_plan": "plan",
                    "update_requirements": "requirements",
                }.get(name, name)
            invalid = 0
        except (DataError, ValueError, KeyError, TypeError) as error:
            row = goals.observation(
                workspace,
                name,
                arguments,
                "",
                error,
                time.monotonic() - started,
            )
            invalid += 1
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(row, ensure_ascii=False),
            }
        )
        if workspace.get("pending_auto_selection") or workspace.get(
            "pending_plan_warning"
        ):
            goal["status"] = "awaiting_confirmation"
            return str(row["result"])
        if (
            name == "search_spots"
            and (workspace.get("spot_preference") or {}).get("status") == "awaiting"
        ):
            goal["status"] = "needs_info"
            return str(row["result"])
        if invalid >= 2:
            break
    goal["status"] = "partial"
    completed = [row for row in goal["observations"] if row["ok"]]
    return f"本轮已完成{len(completed)}项操作，成功的修改与查询结果已保留。部分需求尚未完成，可继续处理或补充必要信息。"
