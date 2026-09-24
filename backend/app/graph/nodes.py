"""LangGraph 节点。

每个节点都是**可单独测试的普通函数**（`AGENTS.md` 要求），签名统一为
`(state: PlanState, runtime: Runtime[TurnContext]) -> dict`，
返回 `PlanState` 的部分更新。

本轮实现的回路（C2）：

```text
parse_request → check_missing_fields
                    ├─ 有关键字段缺失 → ask_clarification →（等待用户补充）
                    └─ 信息齐全       → retrieve_destinations
                                            ├─ 有候选 → recommend_destinations →（等待用户确认）
                                            └─ 无候选 → report_insufficient_data
```

尚未实现（C3 起）：fetch_resources / filter_availability / build_trip_segments /
build_daily_plan / validate_plan / repair_plan / assemble_travel_guide / present_plan /
interpret_change / replan_affected_scope。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Mapping

from langgraph.runtime import Runtime

from app.graph.context import TurnContext
from app.graph.stages import PlanStage
from app.schemas import (
    DateRange,
    PlanState,
    SearchPlanningReadyDestinationsInput,
    TripProfile,
)
from app.services.destination_recommender import DestinationRecommender
from app.services.missing_fields import find_missing_fields
from app.services.request_parser import TripProfileParser
from app.services.travel_mcp_client import TravelMCPClient

#: 节点名（与 LangGraph 图上的名称一致，便于测试与日志定位）
PARSE_REQUEST = "parse_request"
CHECK_MISSING_FIELDS = "check_missing_fields"
ASK_CLARIFICATION = "ask_clarification"
RETRIEVE_DESTINATIONS = "retrieve_destinations"
RECOMMEND_DESTINATIONS = "recommend_destinations"
REPORT_INSUFFICIENT_DATA = "report_insufficient_data"


@dataclass
class NodeDeps:
    """节点的外部依赖。

    所有依赖都以协议形式注入，因此：
      * B 线实现 `TripProfileParser` / `DestinationRecommender` 后可直接替换；
      * A 线实现真实 MCP Server 后可直接替换 `mcp`。
    节点本身不需要改动。
    """

    parser: TripProfileParser
    mcp: TravelMCPClient
    recommender: DestinationRecommender
    known_destinations: Mapping[str, str] = field(default_factory=dict)
    today: Callable[[], date] = date.today


NodeReturn = dict


def build_nodes(deps: NodeDeps) -> dict[str, Callable[..., NodeReturn]]:
    """构造全部节点函数（闭包持有依赖）。"""

    def parse_request(state: PlanState, runtime: Runtime[TurnContext]) -> NodeReturn:
        """把本轮用户输入并入 `TripProfile`。

        只使用用户已经说过的信息，不推测、不补全；缺失情况由下一个节点判定。
        """

        text = (runtime.context.user_message or "").strip()
        profile = deps.parser.parse(
            session_id=state.session_id,
            text=text,
            previous=state.profile,
            reference_date=deps.today(),
            known_destinations=deps.known_destinations,
        )
        profile.missing_fields = find_missing_fields(profile)
        return {
            "profile": profile,
            "stage": PlanStage.PARSING_REQUEST.value,
            "awaiting_user_input": False,
        }

    def check_missing_fields(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """检查影响规划的关键字段是否齐全，并记录到 `missing_fields`。"""

        missing = find_missing_fields(state.profile)
        update: dict = {"stage": PlanStage.CHECKING_FIELDS.value}
        if state.profile is not None:
            profile = state.profile.model_copy(update={"missing_fields": missing})
            update["profile"] = profile
        return update

    def ask_clarification(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """进入追问状态，等待用户补充信息（追问文案由 reply_builder 生成）。"""

        return {
            "stage": PlanStage.ASKING_CLARIFICATION.value,
            "awaiting_user_input": True,
        }

    def retrieve_destinations(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """调用 MCP 获取通过 KnowledgeCoverage 检查的目的地候选。

        只返回候选，不做主观比较；比较交给 `recommend_destinations`。
        """

        profile = state.profile
        request = SearchPlanningReadyDestinationsInput(
            query=_build_query(profile),
            travel_dates=_travel_dates(profile),
            duration_days=profile.duration_days if profile else None,
            traveler_constraints=_constraints(profile),
            top_k=5,
        )
        output = deps.mcp.search_planning_ready_destinations(request)
        if not output.candidates:
            return {
                "destination_candidates": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        # 原始候选只在本轮有效，放在运行期上下文里传给下一个节点
        runtime.context.retrieved = list(output.candidates)
        return {
            "destination_candidates": [],
            "stage": PlanStage.RETRIEVING_DESTINATIONS.value,
        }

    def recommend_destinations(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """在候选集合内做比较，生成推荐理由与证据（B4 的替换点）。"""

        candidates = runtime.context.retrieved
        if not candidates:
            return {
                "destination_candidates": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        recommendations = deps.recommender.recommend(
            profile=state.profile, candidates=candidates, mcp=deps.mcp
        )
        if not recommendations:
            # 有候选但都拿不到证据时，同样不能凭模型记忆给推荐
            return {
                "destination_candidates": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        return {
            "destination_candidates": recommendations,
            "stage": PlanStage.AWAITING_DESTINATION_CONFIRMATION.value,
            "awaiting_user_input": True,
        }

    def report_insufficient_data(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """知识库覆盖不足时的明确降级出口，不伪造推荐结果。"""

        return {
            "stage": PlanStage.INSUFFICIENT_DATA.value,
            "awaiting_user_input": True,
        }

    return {
        PARSE_REQUEST: parse_request,
        CHECK_MISSING_FIELDS: check_missing_fields,
        ASK_CLARIFICATION: ask_clarification,
        RETRIEVE_DESTINATIONS: retrieve_destinations,
        RECOMMEND_DESTINATIONS: recommend_destinations,
        REPORT_INSUFFICIENT_DATA: report_insufficient_data,
    }


# --- 条件边 ----------------------------------------------------------------


def route_after_missing_check(state: PlanState) -> str:
    """信息不全就追问；齐全则去检索候选。"""

    if state.profile is None or state.profile.missing_fields:
        return ASK_CLARIFICATION
    return RETRIEVE_DESTINATIONS


def route_after_retrieve(state: PlanState) -> str:
    """检索到候选才进入推荐，否则走“资料不足”出口。"""

    if state.stage == PlanStage.INSUFFICIENT_DATA.value:
        return REPORT_INSUFFICIENT_DATA
    return RECOMMEND_DESTINATIONS


# --- 辅助 ------------------------------------------------------------------


def _build_query(profile: TripProfile | None) -> str:
    """把画像里的偏好拼成检索/初筛用的查询串。"""

    if profile is None:
        return ""
    parts: list[str] = []
    parts.extend(profile.interests)
    parts.extend(profile.soft_preferences)
    if profile.pace:
        parts.append(profile.pace)
    return " ".join(parts)


def _travel_dates(profile: TripProfile | None) -> DateRange | None:
    if profile is None or profile.start_date is None or profile.end_date is None:
        return None
    return DateRange(start_date=profile.start_date, end_date=profile.end_date)


def _constraints(profile: TripProfile | None) -> list[str]:
    if profile is None:
        return []
    return [*profile.mobility_constraints, *profile.hard_constraints, *profile.avoidances]
