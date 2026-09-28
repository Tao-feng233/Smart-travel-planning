"""高德优先、其余 Mock 的混合 Provider（`DATA_MODE=HYBRID`）。

保持 `V04MockMCPProvider` 的九个工具签名不变：

* `get_route`：先请求高德 Web 服务；成功时返回 `source=PLATFORM` 的真实路线，
  网络超时 / 业务错误 / 空结果 / Key 缺失时回退到现有 Mock 路线，
  **回退结果仍保持 `source=MOCK`**，绝不伪装成高德数据；
* 其余 8 个工具（景点、住宿、餐厅、天气、城际交通、准备规则等）直接委托
  现有 Mock Provider；
* `is_mock_only` 仍为 `True`：整体仍是含 Mock 的 DEMO 数据，
  前端必须继续显示 Mock 警告（`MOCK_DATA_IN_DEMO`）。
"""

from __future__ import annotations

from app.providers.amap_route import AmapRouteClient
from app.schemas import (
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
    SearchPlanningReadyDestinationsRequest,
    SearchPlanningReadyDestinationsResponse,
    SearchResourcesRequest,
    SearchResourcesResponse,
    SearchTravelKnowledgeRequest,
    SearchTravelKnowledgeResponse,
)
from app.services.v04_mock_provider import V04MockMCPProvider

SOURCE_PLATFORM = "PLATFORM"
SOURCE_MOCK = "MOCK"


class HybridMCPProvider:
    """先走高德的 `get_route`，其余工具与失败回退都交给 Mock Provider。"""

    #: 整体仍含 Mock 数据，保留 Mock 警告
    is_mock_only = True

    def __init__(
        self,
        *,
        mock: V04MockMCPProvider | None = None,
        route_client: AmapRouteClient | None = None,
    ) -> None:
        self._mock = mock if mock is not None else V04MockMCPProvider()
        self._route_client = (
            route_client if route_client is not None else AmapRouteClient()
        )
        #: 最近一次 `get_route` 的实际来源（`PLATFORM` / `MOCK`），供降级说明与测试观察
        self.last_route_source: str | None = None

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse:
        live = self._route_client.get_route(request)
        if live is not None and live.routes:
            self.last_route_source = SOURCE_PLATFORM
            return live
        self.last_route_source = SOURCE_MOCK
        return self._mock.get_route(request)

    # --- 其余 8 个工具：原样委托现有 Mock Provider --------------------------

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsRequest
    ) -> SearchPlanningReadyDestinationsResponse:
        return self._mock.search_planning_ready_destinations(request)

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeRequest
    ) -> SearchTravelKnowledgeResponse:
        return self._mock.search_travel_knowledge(request)

    def search_resources(
        self, request: SearchResourcesRequest
    ) -> SearchResourcesResponse:
        return self._mock.search_resources(request)

    def get_resource_facts(
        self, request: GetResourceFactsRequest
    ) -> GetResourceFactsResponse:
        return self._mock.get_resource_facts(request)

    def get_resource_availability(
        self, request: GetResourceAvailabilityRequest
    ) -> GetResourceAvailabilityResponse:
        return self._mock.get_resource_availability(request)

    def get_intercity_options(
        self, request: GetIntercityOptionsRequest
    ) -> GetIntercityOptionsResponse:
        return self._mock.get_intercity_options(request)

    def get_weather(self, request: GetWeatherRequest) -> GetWeatherResponse:
        return self._mock.get_weather(request)

    def get_preparation_rules(
        self, request: GetPreparationRulesRequest
    ) -> GetPreparationRulesResponse:
        return self._mock.get_preparation_rules(request)
