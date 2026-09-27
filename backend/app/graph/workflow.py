"""LangGraph 工作流装配与单轮执行。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.schemas import (
    ItineraryPlan,
    PlanState,
    RunMode,
    TripProfile,
    TripProfileDraft,
)

from .context import TurnContext
from .nodes import (
    ASK_CLARIFICATION,
    CHECK_DESTINATION_CONFIRMATION,
    CHECK_MISSING_FIELDS,
    COMPOSE_GUIDE,
    DETECT_INCIDENT,
    FETCH_RESOURCES,
    FILTER_AVAILABILITY,
    FINISH_TURN,
    PARSE_REQUEST,
    PLAN_ITINERARY,
    RECOMMEND_DESTINATIONS,
    REPLAN_PLAN,
    REPAIR_PLAN,
    REPORT_INSUFFICIENT_DATA,
    RETRIEVE_DESTINATIONS,
    VALIDATE_PLAN,
    NodeDeps,
    build_nodes,
    route_after_incident_detection,
    route_after_filter,
    route_after_fetch,
    route_after_missing_check,
    route_after_retrieve,
    route_after_validation,
)


def build_graph(deps: NodeDeps):
    """构建并编译 P0 阶段（含 C3 前置过滤）的状态图。

    条件边只读取 `PlanState`，不读取运行期上下文，便于单独测试路由函数。
    """

    nodes = build_nodes(deps)
    graph = StateGraph(PlanState, context_schema=TurnContext)

    for name, func in nodes.items():
        graph.add_node(name, func)

    graph.add_edge(START, PARSE_REQUEST)
    graph.add_edge(PARSE_REQUEST, DETECT_INCIDENT)
    graph.add_conditional_edges(
        DETECT_INCIDENT,
        route_after_incident_detection,
        {
            REPLAN_PLAN: REPLAN_PLAN,
            CHECK_MISSING_FIELDS: CHECK_MISSING_FIELDS,
        },
    )
    graph.add_edge(REPLAN_PLAN, VALIDATE_PLAN)
    graph.add_conditional_edges(
        CHECK_MISSING_FIELDS,
        route_after_missing_check,
        {
            ASK_CLARIFICATION: ASK_CLARIFICATION,
            RETRIEVE_DESTINATIONS: RETRIEVE_DESTINATIONS,
        },
    )
    graph.add_edge(ASK_CLARIFICATION, END)
    graph.add_conditional_edges(
        RETRIEVE_DESTINATIONS,
        route_after_retrieve,
        {
            RECOMMEND_DESTINATIONS: RECOMMEND_DESTINATIONS,
            REPORT_INSUFFICIENT_DATA: REPORT_INSUFFICIENT_DATA,
        },
    )
    graph.add_edge(RECOMMEND_DESTINATIONS, FETCH_RESOURCES)
    graph.add_conditional_edges(
        FETCH_RESOURCES,
        route_after_fetch,
        {
            FILTER_AVAILABILITY: FILTER_AVAILABILITY,
            FINISH_TURN: END,
        },
    )
    graph.add_edge(FILTER_AVAILABILITY, CHECK_DESTINATION_CONFIRMATION)
    graph.add_conditional_edges(
        CHECK_DESTINATION_CONFIRMATION,
        route_after_filter,
        {
            PLAN_ITINERARY: PLAN_ITINERARY,
            FINISH_TURN: END,
        },
    )
    graph.add_edge(PLAN_ITINERARY, VALIDATE_PLAN)
    graph.add_conditional_edges(
        VALIDATE_PLAN,
        route_after_validation,
        {
            REPAIR_PLAN: REPAIR_PLAN,
            COMPOSE_GUIDE: COMPOSE_GUIDE,
            FINISH_TURN: END,
        },
    )
    graph.add_edge(COMPOSE_GUIDE, END)
    graph.add_edge(REPAIR_PLAN, VALIDATE_PLAN)
    graph.add_edge(REPORT_INSUFFICIENT_DATA, END)

    return graph.compile()


def run_turn(
    graph,
    state: PlanState,
    user_message: str | None,
    *,
    draft: TripProfileDraft | None = None,
    profile: TripProfile | None = None,
    previous_plan: ItineraryPlan | None = None,
    run_mode: RunMode = RunMode.DEMO,
) -> tuple[PlanState, TurnContext]:
    """推进一轮对话，返回新的 `PlanState` 与本轮上下文。

    图内部使用普通 dict 传状态，这里统一转回契约对象，
    保证任何时刻对外暴露的都是经过校验的 `PlanState`。
    `draft` / `profile` 是会话持有的画像（`CONTRACTS.md` §2.3、§2.4），
    本轮结束后由调用方从返回的上下文里取回并保存。
    """

    context = TurnContext(
        user_message=user_message,
        draft=draft,
        profile=profile,
        run_mode=run_mode,
        previous_stage=state.stage,
        previous_plan=previous_plan,
    )
    raw = graph.invoke(state.model_copy(deep=True), context=context)
    return PlanState.model_validate(raw), context
