"""Semantic goals and a bounded observe/decide/tool loop above business services."""

import copy

from app.integrations.enrichment import model_facts

MODES = {"consult", "query", "delegate", "edit_plan", "explain", "act"}
READ_TOOLS = {
    "review_timeline": (
        "只读审核抵达、返程、道路时间及游玩负担并提出建议；不修改计划或选择",
        {},
    ),
    "refresh_routes": (
        "核对已有选择之间的道路与班次接驳，更新时间轴预览；不重新生成正式计划或改变选择",
        {},
    ),
    "search_spots": (
        "按天数×2推荐候选（2天≥4、3天≥6），底层工具每批最多4个，自动继续取批至目标；recommend_count可指定更多。继续推荐用expand_spots=true补充新候选。无偏好先询问，明确无偏好时preference_mode=default；不替用户选择",
        {
            "recommend_count": {"type": "integer", "minimum": 4, "maximum": 24},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "preference_mode": {"type": "string", "enum": ["default"]},
            "expand_spots": {"type": "boolean"},
        },
    ),
    "search_hotels": (
        "按已有目的地、日期、人数查询酒店；条件不足会返回缺项",
        {"keyword": {"type": "string"}},
    ),
    "search_foods": (
        "按餐次或景点/住宿周边查询餐厅，不保存选择",
        {
            "keywords": {"type": "array", "items": {"type": "string"}},
            "meal_date": {"type": "string"},
            "meal_period": {"type": "string", "enum": ["breakfast", "lunch", "dinner"]},
            "anchor_id": {"type": "string"},
        },
    ),
    "weather": ("查询已有地点坐标的天气；不得编造未覆盖日期", {}),
    "place_detail": ("补充真实候选的营业资料、电话和特色", {"id": {"type": "string"}}),
    "hotel_detail": ("查指定酒店的房型与报价，不自动选择", {"id": {"type": "string"}}),
    "ticket": (
        "查指定景点票务，日期报价缺失保持未知",
        {"id": {"type": "string"}, "visit_date": {"type": "string"}},
    ),
    "train": (
        "查询列车候选；班次必须由用户自行选定",
        {
            "direction": {"type": "string", "enum": ["outbound", "return"]},
            "departure_date": {"type": "string"},
            "train_type": {"type": "string", "enum": ["all", "highspeed", "regular"]},
        },
    ),
    "flight": (
        "查询航班候选；航班必须由用户自行选定",
        {
            "direction": {"type": "string", "enum": ["outbound", "return"]},
            "departure_date": {"type": "string"},
        },
    ),
}


def mission(intent):
    value = intent.get("mission")
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        return None
    objective = value.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        return None
    return {
        "objective": objective[:600],
        "mode": value["mode"],
        "scopes": [
            x
            for x in value.get("scopes", [])
            if x in ("destination", "spots", "hotel", "food")
        ],
        "multi_step": value.get("multi_step") is True,
        "generate_plan": value.get("generate_plan") is True,
    }


def start(w, intent):
    goal = mission(intent)
    if not goal:
        return None
    w["assistant_goal"] = {**goal, "status": "running", "observations": []}
    w["assistant_goal"]["base_revision"] = w.get(
        "turn_base_revision", w.get("revision", 0)
    )
    ids = list(intent.get("select_ids") or []) + list(intent.get("remove_ids") or [])
    if intent.get("replace"):
        directions = {
            w["catalog"][cid].get("direction", "outbound")
            for cid in intent.get("select_ids", [])
            if w.get("catalog", {}).get(cid, {}).get("kind") in ("train", "flight")
        }
        ids += [
            (
                w.get(
                    "selected_return" if direction == "return" else "selected_transport"
                )
                or {}
            ).get("id")
            for direction in directions
        ]
    w["assistant_goal"]["transport_ids"] = [
        cid
        for cid in ids
        if w.get("catalog", {}).get(cid, {}).get("kind") in ("train", "flight")
    ]
    return w["assistant_goal"]


def normalize(w, text, intent):
    """Semantic purpose precedes stage hints; program guards decision authority."""
    value = copy.deepcopy(intent)
    goal = mission(value)
    if not goal:
        return value
    if goal["mode"] in ("query", "consult", "explain"):
        value.pop("preference_updates", None)
        for key in (
            "select_ids",
            "remove_ids",
            "room_id",
            "food_id",
            "meal_mode",
            "visit_requests",
            "visit_order",
        ):
            value.pop(key, None)
        if value["action"] not in set(READ_TOOLS) | {
            "chat",
            "discover_destinations",
            "spots_page",
            "analyze_visits",
            "cancel_auto_selection",
        }:
            value["action"] = "chat"
            goal["multi_step"] = goal["mode"] == "query"
            value["mission"] = goal
        # A hypothetical query must not invalidate an already selected trip.
        protected = {
            "city",
            "origin",
            "start_date",
            "days",
            "adults",
            "children",
            "child_ages",
            "rooms",
            "outbound_date",
            "return_date",
            "end_date",
        }
        protected.update(w.get("requirements", {}))
        selected = any(
            w.get(k)
            for k in (
                "selected_spots",
                "hotel",
                "selected_transport",
                "selected_return",
                "plan",
            )
        )
        changes = {
            k: v
            for k, v in value.get("patch", {}).items()
            if k in protected
            and w["requirements"].get(k) is not None
            and w["requirements"][k] != v
        }
        if selected and changes:
            value.update(
                action="chat",
                patch={},
                answer="本次查询提到的条件与已选行程不同。现有选择已保留；请说明是更改当前旅行，还是仅比较另一方案。",
            )
            goal["multi_step"] = False
            value["mission"] = goal
            value["needs_info"] = True
    if goal["mode"] == "explain":
        value.update(action="chat", patch={})
        value.pop("preference_updates", None)
    if goal["mode"] in ("act", "edit_plan") and (
        goal["multi_step"] or goal["generate_plan"] or goal["mode"] == "edit_plan"
    ):
        value["mission"] = {**goal, "multi_step": True}
    if goal["mode"] == "delegate":
        # Defaults belong in the reviewable proposal, not the known facts.
        evidence = value.get("patch_evidence") or {}
        value["proposed_patch"] = {
            k: v
            for k, v in value.get("patch", {}).items()
            if isinstance(evidence.get(k), str) and evidence[k] and evidence[k] in text
        }
        value["patch"] = {}
    return value


def plan_context(w):
    plan = w.get("plan") or {}
    events = []
    for day in plan.get("days", []):
        for event in day.get("events", []):
            if event.get("kind") in ("free", "rest"):
                continue
            row = {
                k: event.get(k)
                for k in ("kind", "name", "candidate_id", "start", "end", "note")
            }
            row["date"] = day["date"]
            if event.get("route"):
                row["route"] = {
                    k: event["route"].get(k)
                    for k in ("mode", "minutes", "distance", "status")
                }
            events.append(row)
    return {
        "title": plan.get("title"),
        "stale": plan.get("stale"),
        "events": events[:240],
        "events_truncated": len(events) > 240,
        "warnings": plan.get("warnings", [])[:12],
        "conflict": w.get("ui", {}).get("conflict") or w.get("last_plan_conflict"),
    }


def observation(w, name, args, result, error=None, elapsed=0):
    row = {
        "tool": name,
        "arguments": args,
        "result": model_facts(result)
        if isinstance(result, dict)
        else str(result)[:2500],
        "ok": error is None,
        "error": str(error) if error else None,
        "elapsed_ms": round(elapsed * 1000),
    }
    if error is not None and getattr(error, "context", None):
        row["context"] = model_facts(error.context)
    goal = w.get("assistant_goal")
    if goal:
        goal["observations"].append(row)
    return row


def quick_reply(w, name, result):
    if name != "weather":
        return result
    rows = (w.get("weather") or {}).get("days", [])
    if not rows:
        return result
    wanted = w["requirements"].get("start_date")
    rows = [r for r in rows if not wanted or r.get("date") >= wanted][:3]
    if not rows:
        return result + "\n所问日期尚未被当前预报覆盖，不能据此推断天气。"
    text = "\n".join(
        str(r.get("date", ""))
        + "："
        + str(r.get("text") or "天气情况未提供")
        + (
            "，" + str(r["low"]) + "–" + str(r["high"]) + "℃"
            if r.get("low") is not None and r.get("high") is not None
            else ""
        )
        for r in rows
    )
    return text + "\n" + (w.get("weather_note") or "天气可能变化，出发前请再次确认。")


def continue_needed(workspace, goal, action, error=None):
    if not goal.get("multi_step") or goal["mode"] not in (
        "query",
        "act",
        "edit_plan",
        "delegate",
    ):
        return False
    if goal["mode"] == "delegate" and action == "arrange_remaining" and error is None:
        result = workspace.get("auto_selection_result") or {}
        plan = workspace.get("plan") or {}
        return bool(
            workspace.get("auto_selection_run")
            or result.get("errors")
            or goal.get("generate_plan")
            and (not plan or plan.get("stale"))
        )
    return True


def tools(goal=None):
    values = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "additionalProperties": False,
                },
            },
        }
        for name, (description, properties) in READ_TOOLS.items()
    ]
    from app.agents.edit_tools import specifications, schema

    values.extend(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec[0],
                "parameters": schema(spec),
            },
        }
        for name, spec in specifications(goal).items()
    )
    values.append(
        {
            "type": "function",
            "function": {
                "name": "finish_request",
                "description": "基于实际工具结果结束本轮，说明完成项或具体缺项，不编造完成状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["completed", "needs_info", "partial"],
                        },
                    },
                    "required": ["answer", "status"],
                    "additionalProperties": False,
                },
            },
        }
    )
    values.append(
        {
            "type": "function",
            "function": {
                "name": "request_auto_selection",
                "description": "目标需要代选或替换已有内容时申请确认；此工具不执行选择",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "auto_categories": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["destination", "spots", "hotel", "food"],
                            },
                        },
                        "auto_mode": {
                            "type": "string",
                            "enum": ["remaining", "replace"],
                        },
                        "auto_generate_plan": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
            },
        }
    )
    return values


# The implementation lives with the decision/execution loop.
from app.agents.execution import continue_goal as continue_goal
