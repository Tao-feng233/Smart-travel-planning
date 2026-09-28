"""LangGraph 每轮调用的运行期上下文。

`PlanState` 是契约对象（`CONTRACTS.md` §10.2），**不得新增字段**。
因此下面这些只在一轮内部有效、或按契约不属于 `PlanState` 的数据，
都放在 `TurnContext` 里，通过 LangGraph 的 `Runtime` 传入节点：

```text
本轮用户输入             user_message
会话持有的不完整画像     draft      （CONTRACTS.md §2.4，归会话存储）
会话持有的正式画像       profile    （CONTRACTS.md §2.3，归会话存储）
本轮 MCP 原始结果        retrieved / readiness / resources
本轮前置过滤结果         filter_result
```

`PlanState` 只保留契约规定的引用（`trip_profile_version`、
`destination_candidate_ids`、`resource_candidate_ids`），不塞业务对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import (
    DestinationRecommendation,
    DestinationRequest,
    IntercityOption,
    ItineraryPlan,
    PlanningReadinessEvaluation,
    ResourceCandidateBase,
    RunMode,
    TripProfile,
    TripProfileDraft,
    WeatherFact,
)
from app.services.availability_filter import TripFilterResult
from app.services.itinerary_planner import PlanBuildOutcome
from app.services.plan_validator import ValidationResult
from app.services.repair_engine import RepairOutcome
from app.services.guide_service import GuideBuildOutcome


@dataclass
class TurnContext:
    #: 本轮用户输入；None 表示不是由用户消息触发的推进
    user_message: str | None = None
    #: 会话持有的不完整画像（`CONTRACTS.md` §2.4）
    draft: TripProfileDraft | None = None
    #: 会话已确认的正式画像（`CONTRACTS.md` §2.3）；本轮解析成功时被替换
    profile: TripProfile | None = None
    #: 会话的运行模式，影响 `UNKNOWN` 资源能否进入规划（§14 不变量 3）
    run_mode: RunMode = RunMode.DEMO
    #: `search_planning_ready_destinations` 的原始结果（尚未生成推荐）
    retrieved: list[DestinationRecommendation] = field(default_factory=list)
    #: 同一工具的本次就绪度评估（覆盖快照按本次旅行重算，§3.2）
    readiness: list[PlanningReadinessEvaluation] = field(default_factory=list)
    #: 经推荐节点比较后、准备返回给用户的目的地候选
    recommendations: list[DestinationRecommendation] = field(default_factory=list)
    #: 用户已点名目的地时，本轮抓到的原始资源候选
    resources: list[ResourceCandidateBase] = field(default_factory=list)
    #: C3 前置过滤结果（含被排除资源与禁排日期，供 C4/C5 使用）
    filter_result: TripFilterResult | None = None
    #: 进入本轮之前会话所处的阶段（C4 用它判断"用户是不是在回答确认"）
    previous_stage: str | None = None
    #: C4 排程结果（含计划、冲突与降级说明）
    plan_outcome: PlanBuildOutcome | None = None
    #: C5 验证结果
    validation_result: ValidationResult | None = None
    #: 写回验证结论后的计划（`plan_validation_status` / `conflict_ids` 已更新）
    validated_plan: ItineraryPlan | None = None
    #: 会话里已有的计划（C6 重规划要以它为基础，而不是重排一份新的）
    previous_plan: ItineraryPlan | None = None
    #: 本轮识别出的突发事件类型（RAIN / CLOSURE / ...）
    incident_type: str | None = None
    #: C6 修复/重规划结果（含版本谱系）
    repair_outcome: RepairOutcome | None = None
    #: 本轮取到的城际候选（C6 重算费用时要用）
    intercity_options: list[IntercityOption] = field(default_factory=list)
    #: 本轮取到的天气事实（排程用；缺日时为空，不编造）
    weather_facts: list[WeatherFact] = field(default_factory=list)
    #: 上一轮推荐过的目的地候选（用户回「确认」时要用它确定目的地）
    previous_recommendations: list[DestinationRecommendation] = field(default_factory=list)
    #: 本轮被解析器丢弃的"知识库外目的地"（要变成用户可见的 warning）
    dropped_destinations: list[str] = field(default_factory=list)
    #: C7 组装攻略的结果（缺素材时 guide 为 None，但计划仍然有效）
    guide_outcome: GuideBuildOutcome | None = None
