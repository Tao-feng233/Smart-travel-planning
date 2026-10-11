"""Model-callable edits over existing services, with per-action atomic commits."""

import copy

from jsonschema import Draft202012Validator

from app.agents.intent_contract import FUNCTION
from app.core.errors import DataError
from app.integrations.enrichment import model_facts
from app.travel import actions, selections
from app.travel.requirements import update_requirements, mark_stale

INTENT_FIELDS = FUNCTION["function"]["parameters"]["properties"]
ID = {"type": "string", "minLength": 1}
SLOTS = {
    key: INTENT_FIELDS[key]
    for key in ("stay_date", "stay_dates", "meal_date", "meal_period")
}
EDIT_TOOLS = {
    "update_requirements": (
        "保存用户明确修改的条件或偏好。变动条件的evidence须引用本轮用户原文，不用假设消除冲突。",
        {
            "patch": INTENT_FIELDS["patch"],
            "preference_updates": INTENT_FIELDS["preference_updates"],
            "evidence": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        ["patch"],
    ),
    "select_candidate": (
        "选择真实候选；景点重复选择保持不变。酒店按指定夜晚，餐厅按日期餐次；委托安排不选择车票或机票。",
        {"id": ID, "replace": {"type": "boolean"}, **SLOTS},
        ["id"],
    ),
    "remove_candidate": (
        "取消已有选择及关联安排，保留候选资料。指定夜晚/餐次时只取消该位置，否则取消该ID的选择。",
        {"id": ID, **SLOTS},
        ["id"],
    ),
    "replace_candidate": (
        "原子地用同类型真实候选替换已有选择；失败保留原选择。酒店夜晚、餐厅餐次须明确。",
        {"old_id": ID, "new_id": ID, **SLOTS},
        ["old_id", "new_id"],
    ),
    "arrange_remaining": (
        "按明确委托补齐或重选景点、住宿、餐饮；已知条件可直接安排，缺少重要条件时提出可确认方案；交通保留。",
        {
            "auto_categories": INTENT_FIELDS["auto_categories"],
            "auto_mode": INTENT_FIELDS["auto_mode"],
            "auto_generate_plan": {"type": "boolean"},
        },
        [],
    ),
    "continue_arrangement": (
        "继续本次已授权但尚未完成的餐次配置，不重复成功步骤。",
        {},
        [],
    ),
    "generate_plan": (
        "从当前选择生成或修订计划书，保留原版直到新计划成功。缺项后可继续查候选和执行授权修改。",
        {},
        [],
    ),
    "adjust_timeline": (
        "调整建议时间轴；保护固定班次和用户指定条件。",
        {"timeline_changes": INTENT_FIELDS["timeline_changes"]},
        [],
    ),
    "visit_schedule": (
        "记录用户明确的景点日期、时段和顺序。",
        {k: INTENT_FIELDS[k] for k in ("visit_requests", "visit_order")},
        [],
    ),
    "meal_choice": (
        "按用户要求保存餐次选择、删除或自行安排。",
        {
            k: INTENT_FIELDS[k]
            for k in ("meal_date", "meal_period", "meal_mode", "food_id")
        },
        ["meal_date", "meal_period", "meal_mode"],
    ),
    "skip_hotel": ("用户明确自行安排或不需要住宿时跳过住宿，不受房型限制。", {}, []),
    "select_room": (
        "保存用户明确选择的真实房型报价ID；房型仍可选。",
        {"room_id": INTENT_FIELDS["room_id"]},
        ["room_id"],
    ),
    "undo": ("用户明确要求撤销时恢复上一版旅行选择和安排。", {}, []),
}
STATE_TOOL = (
    "获取旅行条件、选择、逐晚住宿、餐次、正式计划、固定约束和真实候选。候选可按类型分页读取，不生成新地点。",
    {
        "kind": {
            "type": "string",
            "enum": ["spot", "hotel", "food", "train", "flight"],
        },
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 80},
    },
    [],
)


def editable(goal):
    return (goal or {}).get("mode") in ("act", "delegate", "edit_plan")


def specifications(goal):
    specs = {"get_travel_state": STATE_TOOL}
    if editable(goal):
        specs.update(EDIT_TOOLS)
    return specs


def schema(spec):
    return {
        "type": "object",
        "properties": spec[1],
        "required": spec[2],
        "additionalProperties": False,
    }


def validate(spec, arguments):
    errors = sorted(
        Draft202012Validator(schema(spec)).iter_errors(arguments),
        key=lambda e: str(e.path),
    )
    if errors:
        raise DataError("工具参数不符合约定：" + errors[0].message[:200])


def state(workspace, arguments):
    from app.agents.goals import plan_context
    from app.planning.schedule import build

    catalog = list(workspace.get("catalog", {}).values())
    if arguments.get("kind"):
        catalog = [p for p in catalog if p.get("kind") == arguments["kind"]]
    offset = arguments.get("offset", 0)
    limit = arguments.get("limit", 40)
    return model_facts(
        {
            "requirements": workspace.get("requirements", {}),
            "selected_spots": workspace.get("selected_spots", []),
            "hotel": workspace.get("hotel"),
            "stay_hotels": workspace.get("stay_hotels", {}),
            "selected_rooms": workspace.get("selected_rooms", {}),
            "meal_choices": workspace.get("meal_choices", {}),
            "meal_mode": workspace.get("meal_mode"),
            "selected_transport": workspace.get("selected_transport"),
            "selected_return": workspace.get("selected_return"),
            "visit_requests": workspace.get("visit_requests", {}),
            "visit_order": workspace.get("visit_order", []),
            "plan": plan_context(workspace),
            "timeline": build(workspace),
            "catalog": catalog[offset : offset + limit],
            "candidate_total": len(catalog),
            "next_offset": offset + limit if offset + limit < len(catalog) else None,
            "pending_confirmation": bool(
                workspace.get("pending_auto_selection")
                or workspace.get("pending_plan_warning")
            ),
            "unfinished_arrangement": bool(workspace.get("auto_selection_run")),
        }
    )


def candidate(workspace, cid):
    place = workspace.get("catalog", {}).get(cid)
    if not place:
        raise DataError("候选不存在，请先查询真实候选。")
    return place


def authorize_candidate(workspace, place):
    goal = workspace.get("assistant_goal") or {}
    kind = place.get("kind")
    if kind in ("train", "flight"):
        if place["id"] not in goal.get("transport_ids", []):
            raise DataError("班次只按用户明确指定的选择修改，本次委托保留交通。")
    scope = {"spot": "spots", "hotel": "hotel", "food": "food"}.get(kind)
    if goal.get("scopes") and scope and scope not in goal["scopes"]:
        raise DataError("该修改超出本轮委托范围，请保留未授权的选择。")


def remove(workspace, cid, arguments):
    place = candidate(workspace, cid)
    authorize_candidate(workspace, place)
    if place.get("kind") == "hotel" and (
        arguments.get("stay_date") or arguments.get("stay_dates")
    ):
        nights = arguments.get("stay_dates") or [arguments["stay_date"]]
        stays = workspace.get("stay_hotels") or {}
        if any(stays.get(day) != cid for day in nights):
            raise DataError("指定夜晚并未选择这家住宿，请核对后修改。")
        workspace["stay_hotels"] = {
            day: hotel for day, hotel in stays.items() if day not in nights
        }
        if cid not in workspace["stay_hotels"].values():
            selections.remove_selection(workspace, cid)
        mark_stale(workspace)
        return True
    if place.get("kind") == "food" and (
        arguments.get("meal_date") or arguments.get("meal_period")
    ):
        if not arguments.get("meal_date") or not arguments.get("meal_period"):
            raise DataError("请同时明确用餐日期和餐次。")
        key = arguments["meal_date"] + "|" + arguments["meal_period"]
        if (workspace.get("meal_choices", {}).get(key) or {}).get("food_id") != cid:
            raise DataError("指定餐次并未选择这家餐厅。")
        del workspace["meal_choices"][key]
        workspace["dining_reviewed"] = False
        mark_stale(workspace)
        return True
    return selections.remove_selection(workspace, cid)


async def select(workspace, cid, arguments, handler, progress):
    place = candidate(workspace, cid)
    authorize_candidate(workspace, place)
    if place.get("stale"):
        raise DataError("候选条件已变化，请重新查询后选择。")
    if place.get("kind") == "spot" and cid in workspace.get("selected_spots", []):
        return "已保留该景点的选择。"
    if place.get("kind") == "hotel" and not (
        arguments.get("stay_date")
        or arguments.get("stay_dates")
        or place.get("stay_date")
    ):
        raise DataError("请选择要入住的夜晚，不自动覆盖其他晚。")
    return await handler(workspace, "select", {"id": cid, **arguments}, progress)


async def perform(workspace, name, arguments, handler, progress):
    scope = {"skip_hotel": "hotel", "select_room": "hotel", "meal_choice": "food"}.get(
        name
    )
    goal = workspace.get("assistant_goal") or {}
    if scope and goal.get("scopes") and scope not in goal["scopes"]:
        raise DataError("该操作超出本轮委托范围。")
    if name == "update_requirements":
        patch = arguments.get("patch", {})
        evidence = arguments.get("evidence") or {}
        question = workspace.get("last_question") or ""
        changed = [
            key
            for key, value in patch.items()
            if workspace["requirements"].get(key) != value
        ]
        if any(
            not evidence.get(key) or evidence[key] not in question for key in changed
        ):
            raise DataError("修改条件需要引用本轮用户原文，不能把推测作为已确认条件。")
        update_requirements(
            workspace, patch, preference_updates=arguments.get("preference_updates")
        )
        return "旅行条件和偏好已更新，受影响的旧计划或报价已标记待更新。"
    if name == "select_candidate":
        return await select(workspace, arguments["id"], arguments, handler, progress)
    if name == "remove_candidate":
        return (
            "已取消该选择及关联安排。"
            if remove(workspace, arguments["id"], arguments)
            else "该候选目前未被选择，已有安排保留。"
        )
    if name == "replace_candidate":
        old = candidate(workspace, arguments["old_id"])
        new = candidate(workspace, arguments["new_id"])
        if old.get("kind") != new.get("kind"):
            raise DataError("只能用同类型候选替换。")
        if old["id"] == new["id"]:
            return "已保留原选择。"
        if not remove(workspace, old["id"], arguments):
            raise DataError("原候选目前未被选择，请先核对旅行状态。")
        slots = {key: arguments[key] for key in SLOTS if key in arguments}
        return await select(
            workspace, new["id"], {**slots, "replace": True}, handler, progress
        )
    if name == "undo":
        from app.persistence import storage

        try:
            base = (workspace.get("assistant_goal") or {}).get(
                "base_revision", workspace["revision"]
            )
            restored = storage.previous({**workspace, "revision": base})
        except ValueError:
            raise DataError("没有可撤销的版本。") from None
        for key in (
            "messages",
            "assistant_goal",
            "last_question",
            "ui",
            "turn_action",
            "turn_base_revision",
            "turn_is_chat",
        ):
            if key in workspace:
                restored[key] = workspace[key]
        workspace.clear()
        workspace.update(restored)
        return "已恢复上一版选择和安排。"
    if name == "continue_arrangement":
        state = workspace.get("auto_selection_run")
        if not state:
            raise DataError("当前没有尚未完成的代选批次。")
        return await handler(
            workspace, "continue_auto_selection", {"approval_id": state["id"]}, progress
        )
    if name == "arrange_remaining":
        goal = workspace.get("assistant_goal") or {}
        categories = (
            arguments.get("auto_categories")
            or goal.get("scopes")
            or ["spots", "hotel", "food"]
        )
        if goal.get("scopes") and any(
            scope not in goal["scopes"] for scope in categories
        ):
            raise DataError("自动安排超出本轮委托范围。")
        return await handler(
            workspace,
            "arrange_remaining",
            {**arguments, "auto_categories": categories},
            progress,
        )
    if name == "generate_plan":
        action = (
            "optimize_plan"
            if workspace.get("plan") or workspace.get("last_plan_conflict")
            else "plan"
        )
        return await handler(
            workspace,
            action,
            {"instruction": workspace.get("last_question", "")},
            progress,
        )
    return await handler(workspace, name, arguments, progress)


async def execute(workspace, name, arguments, handler, progress):
    specs = specifications(workspace.get("assistant_goal"))
    if name not in specs:
        raise DataError("本轮未授权该编辑工具。")
    validate(specs[name], arguments)
    if name == "get_travel_state":
        return state(workspace, arguments)
    draft = copy.deepcopy(workspace)
    answer = await perform(draft, name, arguments, handler, progress)
    actions.commit(workspace, draft)
    return answer
