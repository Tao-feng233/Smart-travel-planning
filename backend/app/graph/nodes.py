"""LangGraph 节点（v0.4 契约）。

每个节点都是**可单独测试的普通函数**（`AGENTS.md` 要求），签名统一为
`(state: PlanState, runtime: Runtime[TurnContext]) -> dict`，
返回 `PlanState` 的部分更新。

本文件实现的回路（C2 + C3）：

```text
parse_request → check_missing_fields
                    ├─ 有关键字段缺失 → ask_clarification →（等待用户补充）
                    └─ 信息齐全       → retrieve_destinations
                                            ├─ 有候选 → recommend_destinations
                                            │             → fetch_resource_candidates
                                            │                 ├─ 用户已点名目的地
                                            │                 │   → filter_availability（C3）
                                            │                 └─ 否则结束，等用户选目的地
                                            └─ 无候选 → report_insufficient_data
```

尚未实现（C4 起）：build_trip_segments / build_daily_plan / validate_plan /
repair_plan / assemble_travel_guide / present_plan / interpret_change /
replan_affected_scope。

**业务约束**（不得违反）：

* 节点只使用 MCP 返回的候选与证据，不引入模型记忆里的旅游事实；
* `UNAVAILABLE` 资源在进入规划之前就被 `filter_availability` 排除；
* 用户点名的目的地如果知识覆盖不达标，也不会出现在推荐候选里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Mapping, Protocol

from langgraph.runtime import Runtime

from app.graph.context import TurnContext
from app.graph.stages import PlanStage
from app.schemas import (
    DateRange,
    DestinationRecommendation,
    GetResourceAvailabilityRequest,
    GetResourceAvailabilityResponse,
    IncompleteProfileError,
    PlanState,
    PlanningReadinessEvaluation,
    ResourceCandidateBase,
    RunMode,
    SearchPlanningReadyDestinationsRequest,
    SearchPlanningReadyDestinationsResponse,
    SearchResourcesRequest,
    SearchResourcesResponse,
    TripProfile,
    finalize_trip_profile,
)
from app.services.availability_filter import TripFilterResult, filter_candidates_for_trip
from app.services.destination_recommender import DestinationRecommender
from app.services.missing_fields import find_missing_fields
from app.services.request_parser import TripProfileParser

#: 节点名（与 LangGraph 图上的名称一致，便于测试与日志定位）
PARSE_REQUEST = "parse_request"
CHECK_MISSING_FIELDS = "check_missing_fields"
ASK_CLARIFICATION = "ask_clarification"
RETRIEVE_DESTINATIONS = "retrieve_destinations"
RECOMMEND_DESTINATIONS = "recommend_destinations"
REPORT_INSUFFICIENT_DATA = "report_insufficient_data"
FETCH_RESOURCES = "fetch_resource_candidates"
FILTER_AVAILABILITY = "filter_availability"

#: 条件边的“本轮到此结束”出口（映射到 LangGraph 的 END）
FINISH_TURN = "finish_turn"

#: 规划前需要抓取的资源类型。住宿属于 C4/P1，暂不抓取。
_RESOURCE_TYPES = ("VISIT_PLACE", "RESTAURANT")


class MCPProvider(Protocol):
    """节点用到的 MCP 工具子集。

    A 线实现真实 MCP Server 后在这里替换即可，节点本身不需要改动。
    """

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsRequest
    ) -> SearchPlanningReadyDestinationsResponse: ...

    def search_resources(self, request: SearchResourcesRequest) -> SearchResourcesResponse: ...

    def get_resource_availability(
        self, request: GetResourceAvailabilityRequest
    ) -> GetResourceAvailabilityResponse: ...


@dataclass
class NodeDeps:
    """节点的外部依赖。

    所有依赖都以协议形式注入，因此：
      * B 线实现 `TripProfileParser` / `DestinationRecommender` 后可直接替换；
      * A 线实现真实 MCP Server 后可直接替换 `mcp`。
    节点本身不需要改动。
    """

    parser: TripProfileParser
    mcp: MCPProvider
    recommender: DestinationRecommender
    known_destinations: Mapping[str, str] = field(default_factory=dict)
    today: Callable[[], date] = date.today


NodeReturn = dict


def build_nodes(deps: NodeDeps) -> dict[str, Callable[..., NodeReturn]]:
    """构造全部节点函数（闭包持有依赖）。"""

    def parse_request(state: PlanState, runtime: Runtime[TurnContext]) -> NodeReturn:
        """把本轮用户输入并入 `TripProfileDraft`，补齐后转换为正式 `TripProfile`。

        只使用用户已经说过的信息，不推测、不补全；关键字段仍缺失时
        不生成正式画像，由下一个节点决定是否追问（`CONTRACTS.md` §2.5）。
        画像内容变化时递增 `profile_version`（§14 不变量 7）。
        """

        text = (runtime.context.user_message or "").strip()
        draft = deps.parser.parse(
            session_id=state.session_id,
            text=text,
            previous=runtime.context.draft,
            reference_date=deps.today(),
            known_destinations=deps.known_destinations,
        )
        draft.missing_fields = draft.compute_missing_fields()
        runtime.context.draft = draft

        update: NodeReturn = {
            "stage": PlanStage.PARSING_REQUEST.value,
            "awaiting_user_input": False,
        }
        if draft.missing_fields:
            return update

        previous = runtime.context.profile
        if previous is not None:
            draft.profile_version = previous.profile_version
        try:
            profile = finalize_trip_profile(draft)
        except IncompleteProfileError as exc:
            # 例如人数与出行人构成不一致：按“还缺信息”处理，不伪造画像
            draft.missing_fields = list(exc.missing_fields)
            runtime.context.draft = draft
            return update

        if previous is not None and not _same_profile(previous, profile):
            profile = profile.model_copy(
                update={"profile_version": previous.profile_version + 1}
            )
        runtime.context.profile = profile
        update["trip_profile_version"] = profile.profile_version
        return update

    def check_missing_fields(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """刷新 Draft 的 `missing_fields`，供追问文案与路由使用。"""

        draft = runtime.context.draft
        missing = find_missing_fields(draft)
        if draft is not None:
            draft.missing_fields = missing
            runtime.context.draft = draft
        # 缺关键字段就一定要问用户，因此本节点结束时“是否等待用户”已经确定
        return {
            "stage": PlanStage.CHECKING_FIELDS.value,
            "awaiting_user_input": bool(missing),
        }

    def ask_clarification(state: PlanState, runtime: Runtime[TurnContext]) -> NodeReturn:
        """关键字段缺失：结束本轮，等用户补充（不在这一轮检索目的地）。"""

        return {
            "stage": PlanStage.ASKING_CLARIFICATION.value,
            "awaiting_user_input": True,
        }

    def retrieve_destinations(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """调用 `search_planning_ready_destinations`，只保留覆盖达标的目的地。"""

        profile = runtime.context.profile
        if profile is None:
            return {
                "destination_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }

        output = deps.mcp.search_planning_ready_destinations(
            SearchPlanningReadyDestinationsRequest(trip_profile=profile, top_k=5)
        )
        runtime.context.readiness = list(output.readiness_evaluations)
        if not output.recommendations:
            return {
                "destination_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        # 原始候选只在本轮有效，放在运行期上下文里传给下一个节点
        runtime.context.retrieved = list(output.recommendations)
        return {
            "destination_candidate_ids": [item.destination_id for item in output.recommendations],
            "stage": PlanStage.RETRIEVING_DESTINATIONS.value,
        }

    def recommend_destinations(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """在候选集合内做比较，生成推荐理由与证据（B4 的替换点）。"""

        candidates = runtime.context.retrieved
        if not candidates:
            return {
                "destination_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        recommendations = deps.recommender.recommend(
            profile=runtime.context.profile,
            candidates=candidates,
            readiness=runtime.context.readiness,
            mcp=deps.mcp,
        )
        if not recommendations:
            # 有候选但都拿不到证据时，同样不能凭模型记忆给推荐
            return {
                "destination_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        runtime.context.recommendations = recommendations
        return {
            "destination_candidate_ids": [item.destination_id for item in recommendations],
            "stage": PlanStage.RECOMMENDING_DESTINATIONS.value,
        }

    def fetch_resource_candidates(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """用户已点名目的地时抓取资源候选；否则本轮到此结束，等用户选目的地。

        用户没点名目的地时不做任何猜测：目的地必须由用户在候选里确认，
        这是 `CONTRACTS.md` §14 状态链里 `RECOMMENDING → WAITING_CONFIRMATION` 的要求。
        """

        profile = runtime.context.profile
        destination_id = _fixed_destination_id(profile)
        if profile is None or destination_id is None:
            return {
                "stage": PlanStage.AWAITING_DESTINATION_CONFIRMATION.value,
                "awaiting_user_input": True,
            }

        date_range = DateRange(start_date=profile.start_date, end_date=profile.end_date)
        resources: list[ResourceCandidateBase] = []
        for resource_type in _RESOURCE_TYPES:
            output = deps.mcp.search_resources(
                SearchResourcesRequest(
                    resource_type=resource_type,
                    destination_id=destination_id,
                    date_range=date_range,
                )
            )
            resources.extend(output.resources)
        runtime.context.resources = resources

        if not resources:
            # 目的地被点名但数据库里没有任何候选：明确报资料不足，不用模型记忆补
            return {
                "destination_candidate_ids": [],
                "resource_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        return {"stage": PlanStage.FILTERING_RESOURCES.value}

    def filter_availability(
        state: PlanState, runtime: Runtime[TurnContext]
    ) -> NodeReturn:
        """C3 前置过滤：`UNAVAILABLE` 资源不得进入规划（§14 不变量 2）。

        逐日检查行程内每一天，因此"整体可用、某几天闭馆"也会被识别：
        全期不可用 → 排除；部分日期不可用 → 保留为有条件候选并记录禁排日期。
        """

        profile = runtime.context.profile
        resources = runtime.context.resources
        if profile is None or not resources:
            return {
                "resource_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }

        result = filter_candidates_for_trip(
            resources,
            travel_dates=_travel_dates(profile),
            availability_lookup=_availability_lookup(deps),
            run_mode=runtime.context.run_mode,
        )
        runtime.context.filter_result = result

        if not result.has_any_candidate:
            return {
                "resource_candidate_ids": [],
                "stage": PlanStage.INSUFFICIENT_DATA.value,
                "awaiting_user_input": True,
            }
        return {
            "resource_candidate_ids": [item.resource_id for item in result.all_candidates],
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
        FETCH_RESOURCES: fetch_resource_candidates,
        FILTER_AVAILABILITY: filter_availability,
    }


# --- 条件边 ----------------------------------------------------------------


def route_after_missing_check(state: PlanState) -> str:
    """信息不全就追问；齐全则去检索候选。"""

    # `check_missing_fields` 已经按缺失情况写好 `awaiting_user_input`
    if state.awaiting_user_input:
        return ASK_CLARIFICATION
    return RETRIEVE_DESTINATIONS


def route_after_retrieve(state: PlanState) -> str:
    """检索到候选才进入推荐，否则走"资料不足"出口。"""

    if state.stage == PlanStage.INSUFFICIENT_DATA.value:
        return REPORT_INSUFFICIENT_DATA
    return RECOMMEND_DESTINATIONS


def route_after_fetch(state: PlanState) -> str:
    """抓到资源候选才做前置过滤，否则本轮结束（等用户确认目的地）。"""

    if state.stage == PlanStage.FILTERING_RESOURCES.value:
        return FILTER_AVAILABILITY
    return FINISH_TURN


# --- 辅助 ------------------------------------------------------------------


def _same_profile(previous: TripProfile, current: TripProfile) -> bool:
    """比较两份画像的业务内容（忽略版本号本身）。"""

    exclude = {"profile_version"}
    return previous.model_dump(exclude=exclude) == current.model_dump(exclude=exclude)


def _fixed_destination_id(profile: TripProfile | None) -> str | None:
    """用户是否已经点名了一个确定的目的地（多目的地属于 P1）。"""

    if profile is None:
        return None
    fixed = [item for item in profile.destination_requests if item.fixed]
    if len(fixed) == 1:
        return fixed[0].destination_id
    if not fixed and profile.destination_mode == "SINGLE" and len(profile.destination_requests) == 1:
        return profile.destination_requests[0].destination_id
    return None


def _travel_dates(profile: TripProfile) -> list[date]:
    """行程覆盖的每一天（含首尾），§14 不变量 9 要求日期完整覆盖。"""

    span = (profile.end_date - profile.start_date).days
    return [profile.start_date + timedelta(days=offset) for offset in range(span + 1)]


def _availability_lookup(deps: NodeDeps):
    """把 MCP 的 `get_resource_availability` 适配成过滤器需要的纯查询函数。"""

    def lookup(resource_id: str, travel_date: date) -> GetResourceAvailabilityResponse:
        return deps.mcp.get_resource_availability(
            GetResourceAvailabilityRequest(resource_id=resource_id, date=travel_date)
        )

    return lookup
