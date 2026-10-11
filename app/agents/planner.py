from app.agents import input_context, turn
from app.travel import hotels
from app.agents import recommendations
from app import prompts
import json
from datetime import date, timedelta
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.core.errors import DataError
from app.integrations.providers import llm, tuniu
from app.integrations.tools import local_tool
from app.planning.engine import generate, route_options, choose_route
from app.integrations import enrichment


def hotel_services():
    """Bind current clients at the entry point; handlers own no agent globals."""
    return hotels.HotelServices(
        tuniu, local_tool, route_options, choose_route, hotel_query_budget
    )


async def search_hotels(w, args, progress, recommend):
    return await hotels.search(w, args, progress, recommend, hotel_services())


async def search_hotels_by_keyword(w, args, progress, recommend):
    return await hotels.search_keyword(w, args, progress, recommend, hotel_services())


async def hotel_query_budget():
    """Remaining query reservations across configured independent Tuniu accounts."""
    from app.integrations.tuniu_pool import remaining_budget

    return remaining_budget()


async def load_hotel_detail(w, p, progress):
    return await hotels.load_detail(w, p, progress, hotel_services())


class GraphState(TypedDict):
    workspace: dict
    text: str
    progress: object
    intent: dict
    answer: str
    attempts: int
    feedback: str
    route: str


from app.agents.intent_contract import FUNCTION, ACTIONS


def parse_intent(m):
    """Model output is a proposal: reject anything that is not one valid submit_intent call."""
    calls = m["tool_calls"]
    if len(calls) != 1 or calls[0]["function"]["name"] != "submit_intent":
        raise ValueError("未返回唯一的 submit_intent 调用")
    intent = json.loads(calls[0]["function"]["arguments"])
    if not isinstance(intent, dict) or intent.get("action") not in ACTIONS:
        raise ValueError("action 不在允许的动作集合内")
    return intent


async def understand(s):
    w = s["workspace"]
    s["progress"]("主助手正在理解用户目标与决定范围")
    prompt = prompts.system("intent")

    context = input_context.intent_context(w, s["text"])
    messages = [{"role": "system", "content": prompt}]
    if s.get("feedback"):
        messages.append({"role": "user", "content": s["feedback"]})
    messages.append(
        {
            "role": "user",
            "content": json.dumps(enrichment.model_facts(context), ensure_ascii=False),
        }
    )
    m, u = await llm(messages, tools=[FUNCTION], label="understand")
    w["last_usage"] = u
    try:
        intent = parse_intent(m)
    except (KeyError, ValueError, TypeError) as e:
        # Bounded repair: this node is entered at most twice; a second unusable
        # answer is reported instead of looping.
        if (s.get("attempts") or 0) >= 1:
            raise DataError("模型没有返回可执行动作，请重新描述需求") from None
        return {
            "intent": None,
            "feedback": "上一次输出不可用（"
            + type(e).__name__
            + "）。请严格调用 submit_intent：action 只能取给定枚举之一，patch 只填写用户本轮明确说过的条件。",
        }
    return {"intent": intent, "feedback": ""}


def check_intent(s):
    """Conditional edge: only loop back when the previous answer was unusable."""
    attempts = (s.get("attempts") or 0) + 1
    intent = s.get("intent")
    if isinstance(intent, dict) and intent.get("action") in ACTIONS:
        return {"attempts": attempts, "route": "execute"}
    return {"attempts": attempts, "route": "understand"}


async def execute(s):
    return await turn.execute(s, turn.TurnServices(llm, handle, ensure_weather))


graph = StateGraph(GraphState)
graph.add_node("understand", understand)
graph.add_node("check", check_intent)
graph.add_node("execute", execute)
graph.add_edge(START, "understand")
graph.add_edge("understand", "check")
# The cycle is the reason this graph is worth having: an unusable model answer
# is retried once with concrete feedback, then reported.
graph.add_conditional_edges(
    "check",
    lambda s: s.get("route", "execute"),
    {"execute": "execute", "understand": "understand"},
)
graph.add_edge("execute", END)
AGENT = graph.compile()


async def recommend(w, items, task, guides=None):
    return await recommendations.recommend(
        w, items, task, guides, model=llm, ensure_weather=ensure_weather
    )


async def handle(w, action, args, progress):
    from app.agents.action_services import ActionServices
    from app.travel.dispatch import dispatch

    services = ActionServices(
        llm=llm,
        tuniu=tuniu,
        local_tool=local_tool,
        recommend=recommend,
        handle=handle,
        generate=generate,
        route_options=route_options,
        choose_route=choose_route,
        search_hotels=search_hotels,
        load_hotel_detail=load_hotel_detail,
    )
    return await dispatch(w, action, args, progress, services)


async def run_chat(w, text, progress):
    result = await AGENT.ainvoke({"workspace": w, "text": text, "progress": progress})
    w["last_action"] = w.get("turn_action") or (result.get("intent") or {}).get(
        "action", "chat"
    )
    return result["answer"]


async def ensure_weather(w, progress):
    r = w["requirements"]
    if not r.get("city") or not r.get("start_date"):
        return
    key = [r["city"], r["start_date"], r.get("days")]
    if w.get("weather_for") == key:
        return
    candidates = [w["catalog"].get(i, {}) for i in w.get("selected_spots", [])] + list(
        w.get("catalog", {}).values()
    )
    p = next(
        (p for p in candidates if p.get("kind") == "spot" and p.get("location")), None
    )
    if not p:
        return
    progress("正在核对旅行日期的天气")
    try:
        w["weather"] = await local_tool("daily_weather", {"location": p["location"]})
        w["weather_for"] = key
        w["turn_weather_updated"] = True
        lead = (date.fromisoformat(r["start_date"]) - date.today()).days
        days = w["weather"].get("days", [])
        relevant = [
            d
            for d in days
            if r["start_date"]
            <= d["date"]
            < (
                date.fromisoformat(r["start_date"])
                + timedelta(days=int(r.get("days") or 1))
            ).isoformat()
        ]
        w["weather_note"] = (
            "出行日期距离今天较远，预报存在较大不确定性，请临近出发时再次查询。"
            if lead >= 5
            else "天气可能变化，请出发前再次确认。"
        )
        unknown = int(r.get("days") or 1) - len(relevant)
        if relevant and unknown > 0:
            w["weather_note"] += (
                f" 本次还有{unknown}天超出当前预报覆盖，届时需另行查询。"
            )
        if not relevant:
            w["weather_note"] = (
                "出行日期超出当前预报窗口，尚无该日期的可靠预报，请临近出发时查询。"
            )
    except DataError:
        w["weather_note"] = (
            "本次暂未取得天气数据，可稍后重新查询；其他规划步骤可以继续。"
        )
