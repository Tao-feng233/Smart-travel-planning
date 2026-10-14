"""One conversation turn: interpret, acknowledge, execute and finish."""

import time
from dataclasses import dataclass
from typing import Callable
from app.core.errors import DataError
from app.core.text import readable
from app.application import guidance
from app.agents import goals as goal_agent, replies
from app.agents.auto_selection import delegation
from app.agents.recommendation_context import needs_preferences, ask
from app.planning.plan_revision import refine
from app.travel import discovery, journey, actions as travel_actions
from app.travel.requirements import update_requirements


@dataclass(frozen=True)
class TurnServices:
    model: Callable
    handler: Callable
    ensure_weather: Callable


@dataclass
class Turn:
    workspace: dict
    intent: dict
    progress: Callable
    services: TurnServices
    goal: dict | None
    action: str
    before: dict
    patch: dict


async def prepare(s, services):
    w = s["workspace"]
    semantic = goal_agent.mission(s["intent"])
    parsed = (
        goal_agent.normalize(w, s.get("text", ""), s["intent"])
        if semantic
        else journey.refine_intent(w, s.get("text", ""), s["intent"])
    )
    delegated = delegation(w, s.get("text", ""), parsed)
    intent = delegated if semantic else refine(w, s.get("text", ""), delegated)
    goal = goal_agent.start(w, intent)
    w["last_question"] = s.get("text", "")
    w["turn_is_chat"] = True
    w["turn_food_updated"] = False
    w["turn_weather_updated"] = False
    w["turn_action"] = intent.get("action", "chat")
    w["turn_result"] = ""
    before = dict(w["requirements"])
    patch = intent.get("patch", {})
    # 本地语料未覆盖的目的地：先联网取证（Tavily + trust_score），拿不到可信资料仍按原样拒绝。
    from app.knowledge import web_fallback

    city = patch.get("city")
    origin = (
        await web_fallback.admit(w, city, s.get("progress"))
        if city
        else web_fallback.source(w, w["requirements"].get("city"))
    )
    if intent.get("requested_place") and origin != "web":
        from app.knowledge.coverage import require_place

        require_place(
            patch.get("city") or w["requirements"].get("city"),
            intent["requested_place"],
        )
    update_requirements(w, patch, preference_updates=intent.get("preference_updates"))
    action = intent.get("action", "chat")
    if action == "spots_page" and not intent.get("page") and w.get("spot_search"):
        info = discovery.page_info(w)
        if info["page"] >= info["pages"]:
            action = "search_spots"
            intent["expand_spots"] = True
    return Turn(w, intent, s["progress"], services, goal, action, before, patch)


def acknowledge(turn):
    w, intent, goal, action = turn.workspace, turn.intent, turn.goal, turn.action
    before, patch = turn.before, turn.patch
    facts = []
    for key, label in [
        ("start_date", "出发日期"),
        ("days", "天数"),
        ("adults", "成人数"),
        ("origin", "出发地"),
        ("return_date", "返程日期"),
        ("outbound_date", "去程日期"),
    ]:
        if key in patch and before.get(key) != w["requirements"].get(key):
            facts.append(f"{label}：{w['requirements'][key]}")
    if facts:
        replies.acknowledge(
            (
                intent.get("acknowledgement", "") + "\n"
                if intent.get("acknowledgement")
                else ""
            )
            + "已收集旅行信息：**"
            + "，".join(facts)
            + "**。"
            + (
                "下面查询住宿，并核对旅行日期的天气。"
                if action == "search_hotels"
                else "下面按这些条件查询相关信息。"
            )
        )
    if action == "visit_schedule" and not replies.PREFIX.get():
        replies.acknowledge(
            "好的，将为这些景点记录指定日期与时段，生成或重排时会核对。"
        )
    if not facts and not replies.PREFIX.get() and intent.get("acknowledgement"):
        replies.acknowledge(intent["acknowledgement"])
    elif not facts and not replies.PREFIX.get() and action not in ("chat", "plan"):
        replies.acknowledge(
            "已了解您的要求。"
            + (
                "重新筛选城市代表景点，同时保留您的餐饮偏好。"
                if intent.get("prefer_known")
                else "我会根据您的要求继续处理当前安排。"
            )
        )


ARGUMENT_FIELDS = (
    "recommend_count",
    "requested_place",
    "expand_spots",
    "page",
    "timeline_changes",
    "stay_date",
    "stay_dates",
    "preference_mode",
    "proposed_patch",
    "allow_missing",
    "auto_generate_plan",
    "instruction",
    "conflict",
    "auto_mode",
    "auto_categories",
    "id",
    "view",
    "visit_date",
    "keyword",
    "room_id",
    "replace",
    "time_start",
    "time_end",
    "train_type",
    "food_keywords",
    "prefer_known",
    "auto_select",
    "meal_mode",
    "meal_date",
    "meal_period",
    "food_id",
    "departure_date",
    "anchor_id",
    "visit_requests",
    "visit_order",
)


def action_arguments(intent):
    return {
        "keywords": intent.get("keywords", []),
        "direction": intent.get("direction", "outbound"),
        "reject_current": intent.get("reject_current", False),
        **{key: intent[key] for key in ARGUMENT_FIELDS if key in intent},
    }


async def first_action(turn, arguments):
    w, intent, goal, action = turn.workspace, turn.intent, turn.goal, turn.action
    started = time.monotonic()
    tool_error = None
    try:
        answer = await travel_actions.run(
            w, action, arguments, turn.progress, turn.services.handler
        )
    except DataError as error:
        if not goal or not (
            goal["multi_step"] or goal["mode"] in ("query", "edit_plan")
        ):
            raise
        tool_error = error
        answer = ""
    first = goal_agent.observation(
        w, action, arguments, answer, tool_error, time.monotonic() - started
    )
    return answer, tool_error, first


async def extra_food(turn, answer):
    w, intent, goal, action = turn.workspace, turn.intent, turn.goal, turn.action
    if (
        intent.get("include_food") or w["requirements"].get("food_preferences")
    ) and action in ("search_spots", "spots_page"):
        try:
            answer += "\n" + await turn.services.handler(
                w,
                "search_foods",
                {
                    "keywords": intent.get("food_keywords")
                    or w["requirements"].get("food_preferences")
                },
                turn.progress,
            )
            w["ui"] = guidance.describe(w, action, view="spot", status="loading")
        except DataError:
            answer += "\n本次未取得餐饮候选，已保留餐饮偏好，可稍后单独查询。"
    return answer


async def finish_goal(turn, answer, tool_error, first):
    w, intent, goal, action = turn.workspace, turn.intent, turn.goal, turn.action
    loop_answer = False
    if goal:
        if action == "request_auto_selection":
            goal["status"] = "awaiting_confirmation"
        elif goal_agent.continue_needed(w, goal, action, tool_error):
            answer = await goal_agent.continue_goal(
                w, first, turn.services.model, turn.services.handler, turn.progress
            )
            loop_answer = True
        elif tool_error or intent.get("needs_info"):
            goal["status"] = "needs_info"
            answer = str(tool_error) if tool_error else intent["answer"]
        else:
            goal["status"] = (
                "awaiting_confirmation"
                if w.get("pending_auto_selection") or w.get("pending_plan_warning")
                else "running"
                if w.get("auto_selection_run")
                else "partial"
                if action == "arrange_remaining"
                and (w.get("auto_selection_result") or {}).get("errors")
                else "completed"
            )
            answer = goal_agent.quick_reply(w, action, answer)
    return answer, loop_answer


async def execute(s, services):
    if not isinstance(s.get("intent"), dict):
        raise DataError("模型没有返回可执行动作，请重新描述需求")
    turn = await prepare(s, services)
    w, intent, goal, action = turn.workspace, turn.intent, turn.goal, turn.action
    if action == "search_spots" and needs_preferences(w, intent):
        answer = ask(w)
        w["ui"] = guidance.describe(w, "chat", view="spot", status="loading")
        w.update(last_action="chat", turn_action="chat", turn_result=answer)
        if goal:
            goal["status"] = "needs_info"
        return {"answer": answer}
    w["ui"] = guidance.describe(w, action, view=intent.get("view"), status="loading")
    turn.progress(w["ui"]["title"])
    acknowledge(turn)
    if action != "request_auto_selection" and not goal:
        await services.ensure_weather(w, turn.progress)
    selection_answer = await travel_actions.apply_choices(
        w, intent, turn.progress, services.handler
    )
    answer, tool_error, first = await first_action(turn, action_arguments(intent))
    answer = await extra_food(turn, answer)
    if selection_answer:
        answer = selection_answer + "\n" + (answer or "")
    answer, loop_answer = await finish_goal(turn, answer, tool_error, first)
    w["turn_result"] = answer or intent.get("answer", "")
    w["turn_next"] = journey.next_step(w)
    answer = readable(
        answer
        or selection_answer
        or intent.get("answer", "请选择候选，或补充旅行信息。")
    )
    if not goal:
        await services.ensure_weather(w, turn.progress)
    w["last_action"] = w.get("turn_action", action)
    quick = (
        goal and goal["mode"] in ("query", "act", "explain") and not goal["multi_step"]
    )
    if replies.SINK.get() and not loop_answer and not quick:
        answer = await replies.compose(w, answer)
    return {"answer": answer}
