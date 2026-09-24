"""v0.4 契约对象包。

本包是 `CONTRACTS.md` v0.4 的可执行实现，由成员 C 维护。
A、B 只能导入这里的对象，不得复制定义或自行补字段
（`docs/SHARED_SCHEMA_HANDOFF.md`）。

模块划分：

```text
models.py        契约基线：枚举、通用类型、需求/覆盖/事实/资源/行程/攻略
planning.py      验证与冲突：Conflict / RepairOption / AlternativePlan
candidates.py    资源判别联合类型 ResourceCandidateUnion
state.py         PlanState / VersionLineage / UserAction
mcp.py           9 个 MCP 工具的 Request / Response
rest.py          REST 统一响应信封与各接口请求响应
```
"""

from .candidates import (
    RESOURCE_CANDIDATE_ADAPTER,
    ResourceCandidateBase,
    ResourceCandidateUnion,
    parse_resource_candidate,
)
from .mcp import (
    MCP_TOOL_MODELS,
    DateRange,
    GetIntercityOptionsRequest,
    GetIntercityOptionsResponse,
    GetPreparationRulesRequest,
    GetPreparationRulesResponse,
    GetResourceAvailabilityRequest,
    GetResourceAvailabilityResponse,
    GetResourceFactsRequest,
    GetResourceFactsResponse,
    GetRouteRequest,
    GetRouteResponse,
    GetWeatherRequest,
    GetWeatherResponse,
    RouteOption,
    SearchPlanningReadyDestinationsRequest,
    SearchPlanningReadyDestinationsResponse,
    SearchResourcesRequest,
    SearchResourcesResponse,
    SearchTravelKnowledgeRequest,
    SearchTravelKnowledgeResponse,
    WeatherFact,
)
from .models import *  # noqa: F401,F403
from .models import MODEL_REGISTRY as _BASELINE_REGISTRY
from .models import LodgingAreaCandidate
from .planning import Conflict, ConflictType, RepairAction, RepairOption
from .recommendation import DestinationRecommendation
from .rest import (
    ConfirmGuideData,
    ConfirmGuideRequest,
    CreateSessionData,
    CreateSessionRequest,
    Envelope,
    ErrorCode,
    ErrorDetail,
    GetGuideData,
    GuideChangeData,
    ModifyGuideRequest,
    RefreshGuideData,
    RefreshGuideRequest,
    SendMessageData,
    SendMessageRequest,
    WarningItem,
)
from .state import (
    ActionChangePayload,
    ActionType,
    ChangeType,
    PlanState,
    ReplacementRelation,
    ScopeHint,
    UserAction,
    VersionLineage,
)

#: 契约测试用的模型注册表：基线 11 个 + C1 补齐的对象。
MODEL_REGISTRY: dict[str, type] = {
    **_BASELINE_REGISTRY,
    "DestinationRecommendation": DestinationRecommendation,
    "ResourceCandidateBase": ResourceCandidateBase,
    "LodgingAreaCandidate": LodgingAreaCandidate,
    "RepairOption": RepairOption,
    "Conflict": Conflict,
    "PlanState": PlanState,
    "VersionLineage": VersionLineage,
    "UserAction": UserAction,
    "DateRange": DateRange,
    "RouteOption": RouteOption,
    "WeatherFact": WeatherFact,
    "SearchPlanningReadyDestinationsRequest": SearchPlanningReadyDestinationsRequest,
    "SearchPlanningReadyDestinationsResponse": SearchPlanningReadyDestinationsResponse,
    "SearchTravelKnowledgeRequest": SearchTravelKnowledgeRequest,
    "SearchTravelKnowledgeResponse": SearchTravelKnowledgeResponse,
    "SearchResourcesRequest": SearchResourcesRequest,
    "SearchResourcesResponse": SearchResourcesResponse,
    "GetResourceFactsRequest": GetResourceFactsRequest,
    "GetResourceFactsResponse": GetResourceFactsResponse,
    "GetResourceAvailabilityRequest": GetResourceAvailabilityRequest,
    "GetResourceAvailabilityResponse": GetResourceAvailabilityResponse,
    "GetIntercityOptionsRequest": GetIntercityOptionsRequest,
    "GetIntercityOptionsResponse": GetIntercityOptionsResponse,
    "GetRouteRequest": GetRouteRequest,
    "GetRouteResponse": GetRouteResponse,
    "GetWeatherRequest": GetWeatherRequest,
    "GetWeatherResponse": GetWeatherResponse,
    "GetPreparationRulesRequest": GetPreparationRulesRequest,
    "GetPreparationRulesResponse": GetPreparationRulesResponse,
    "CreateSessionRequest": CreateSessionRequest,
    "CreateSessionData": CreateSessionData,
    "SendMessageRequest": SendMessageRequest,
    "SendMessageData": SendMessageData,
    "ConfirmGuideRequest": ConfirmGuideRequest,
    "ConfirmGuideData": ConfirmGuideData,
    "ModifyGuideRequest": ModifyGuideRequest,
    "GuideChangeData": GuideChangeData,
    "RefreshGuideRequest": RefreshGuideRequest,
    "RefreshGuideData": RefreshGuideData,
    "Envelope": Envelope,
}

__all__ = [name for name in dir() if not name.startswith("_")]
