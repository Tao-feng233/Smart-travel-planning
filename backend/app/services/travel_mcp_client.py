"""旅游 MCP Client。

`CONTRACTS.md` §12 规定所有外部事实通过旅游 MCP Server 暴露给 LangGraph。
C 的节点只依赖本文件定义的 `TravelMCPClient` 协议，不直接访问 MySQL、Chroma 或任何外部 API。

P0 阶段使用 `FakeTravelMCPClient`（数据来自 `fake_data.py`，全部 MOCK_ONLY）。
**替换点**：A 线完成真实 MCP Server 后，新增 `RemoteTravelMCPClient`（通过 MCP 协议调用）
并在 `app/api/deps.py` 中切换，节点代码不需要改动。
"""

from __future__ import annotations

import hashlib
import math
from datetime import date
from typing import Protocol

from app.schemas.legacy import (
    AcquisitionStatus,
    AvailabilityStatus,
    GetPlaceAvailabilityInput,
    GetPlaceAvailabilityOutput,
    GetPlaceFactsInput,
    GetPlaceFactsOutput,
    GetRouteInput,
    GetRouteOutput,
    GetWeatherInput,
    GetWeatherOutput,
    KnowledgeCoverage,
    PlanningReadyDestination,
    ResourceType,
    SearchPlanningReadyDestinationsInput,
    SearchPlanningReadyDestinationsOutput,
    SearchTravelKnowledgeInput,
    SearchTravelKnowledgeOutput,
    SourceType,
    TemperatureRange,
    TravelLegSource,
    TravelMode,
)

from . import fake_data


class TravelMCPClient(Protocol):
    """旅游 MCP Server 的客户端接口（与 `CONTRACTS.md` §12 一一对应）。"""

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsInput
    ) -> SearchPlanningReadyDestinationsOutput: ...

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeInput
    ) -> SearchTravelKnowledgeOutput: ...

    def get_place_facts(self, request: GetPlaceFactsInput) -> GetPlaceFactsOutput: ...

    def get_place_availability(
        self, request: GetPlaceAvailabilityInput
    ) -> GetPlaceAvailabilityOutput: ...

    def get_route(self, request: GetRouteInput) -> GetRouteOutput: ...

    def get_weather(self, request: GetWeatherInput) -> GetWeatherOutput: ...


#: 每个游玩地点每天最多安排的景点数与最少替代项要求（P0 可配置规则）。
MIN_PLACES_PER_DAY = 2


def recompute_planning_ready(
    coverage: KnowledgeCoverage, duration_days: int | None
) -> bool:
    """按本次旅行的天数重新计算 `planning_ready`。

    `CONTRACTS.md` §2 要求覆盖阈值“根据用户天数和攻略要求重新计算”，
    而不是固定判断。本条规则属于**数据覆盖检查**，真实实现应放在 A 线的
    KnowledgeCoverage 服务里；这里只是让 C 线能跑通前置过滤。
    """

    if not coverage.planning_ready:
        return False
    if duration_days is None:
        return True
    # 需要覆盖用户天数所需的地点，并保留至少一个替代项
    required = duration_days * MIN_PLACES_PER_DAY + 1
    if coverage.visit_place_count < required:
        return False
    return (
        coverage.opening_rule_coverage >= 0.6
        and coverage.route_coverage >= 0.5
        and coverage.lodging_coverage >= 0.5
    )


class FakeTravelMCPClient:
    """C 线自用模拟实现。任何返回值都来自 `fake_data`（MOCK_ONLY）。"""

    #: 供上层标注降级：本实现返回的全部是模拟数据
    is_mock_only = True

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsInput
    ) -> SearchPlanningReadyDestinationsOutput:
        duration = request.duration_days
        ready: list[PlanningReadyDestination] = []
        for item in fake_data.DESTINATIONS:
            coverage = item["coverage"]
            if not recompute_planning_ready(coverage, duration):
                continue
            if not _matches_query(request.query, item):
                continue
            ready.append(
                PlanningReadyDestination(
                    destination_id=item["destination_id"],
                    name=item["name"],
                    coverage_version=coverage.coverage_version,
                    planning_ready=True,
                    coverage=coverage,
                )
            )
        return SearchPlanningReadyDestinationsOutput(candidates=ready[: request.top_k])

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeInput
    ) -> SearchTravelKnowledgeOutput:
        results = []
        for evidence in fake_data.EVIDENCE:
            if request.destination_ids:
                entity_destination = _destination_of(evidence.entity_id)
                if entity_destination not in request.destination_ids:
                    continue
            if request.resource_type is not None and not _entity_matches_type(
                evidence.entity_id, request.resource_type
            ):
                continue
            if request.query and not _keyword_overlap(request.query, evidence.content):
                # 关键词不命中时仍然返回该实体的证据，避免模拟数据过少导致空结果，
                # 但把命中项排在前面。
                pass
            results.append(evidence)
        hits = [e for e in results if _keyword_overlap(request.query, e.content)]
        others = [e for e in results if e not in hits]
        ordered = hits + others
        return SearchTravelKnowledgeOutput(evidence=ordered[: request.top_k])

    def get_place_facts(self, request: GetPlaceFactsInput) -> GetPlaceFactsOutput:
        facts = [
            fact
            for resource_id in request.resource_ids
            if (fact := fake_data.find_resource(resource_id)) is not None
        ]
        return GetPlaceFactsOutput(facts=facts)

    def get_place_availability(
        self, request: GetPlaceAvailabilityInput
    ) -> GetPlaceAvailabilityOutput:
        resource = fake_data.find_resource(request.resource_id)
        if resource is None:
            return GetPlaceAvailabilityOutput(
                status=AvailabilityStatus.UNKNOWN,
                reason=f"未收录资源 {request.resource_id}",
                evidence_ids=[],
            )
        availability = resource.availability
        if availability.status is AvailabilityStatus.UNAVAILABLE:
            return GetPlaceAvailabilityOutput(
                status=availability.status,
                time_windows=availability.time_windows,
                reservation_required=availability.reservation_required,
                reason=availability.reason,
                evidence_ids=resource.evidence_ids,
            )
        if availability.valid_dates and request.date not in availability.valid_dates:
            return GetPlaceAvailabilityOutput(
                status=AvailabilityStatus.UNKNOWN,
                time_windows=availability.time_windows,
                reservation_required=availability.reservation_required,
                reason="该日期缺少可用性数据",
                evidence_ids=resource.evidence_ids,
            )
        return GetPlaceAvailabilityOutput(
            status=availability.status,
            time_windows=availability.time_windows,
            reservation_required=availability.reservation_required,
            reason=availability.reason,
            evidence_ids=resource.evidence_ids,
        )

    def get_route(self, request: GetRouteInput) -> GetRouteOutput:
        mode = request.mode or TravelMode.WALK
        distance_km = _distance_km(
            fake_data.find_resource(request.origin),
            fake_data.find_resource(request.destination),
        )
        speed_kmh = {
            TravelMode.WALK: 4.5,
            TravelMode.BIKE: 12.0,
            TravelMode.BUS: 18.0,
            TravelMode.METRO: 25.0,
            TravelMode.TAXI: 22.0,
            TravelMode.OTHER: 15.0,
        }[mode]
        # 固定加上换乘/等候时间，避免出现“门到门比直线速度还快”的失真结果
        duration = round(distance_km / speed_kmh * 60) + (8 if mode is not TravelMode.WALK else 0)
        cost = {
            TravelMode.WALK: 0.0,
            TravelMode.BIKE: 1.5,
            TravelMode.BUS: 2.0,
            TravelMode.METRO: 4.0,
            TravelMode.TAXI: round(10 + distance_km * 2.6, 1),
            TravelMode.OTHER: None,
        }[mode]
        return GetRouteOutput(
            duration_minutes=max(duration, 5),
            distance_km=round(distance_km, 2),
            estimated_cost=cost,
            source=TravelLegSource.FAKE,
            is_estimated=True,
            mode=mode,
        )

    def get_weather(self, request: GetWeatherInput) -> GetWeatherOutput:
        digest = hashlib.sha256(
            f"{request.destination_id}:{request.date.isoformat()}".encode("utf-8")
        ).digest()
        conditions = ["晴", "多云", "阴", "小雨", "中雨"]
        condition = conditions[digest[0] % len(conditions)]
        base = 14 + digest[1] % 12
        precipitation = {
            "晴": 0.05,
            "多云": 0.15,
            "阴": 0.3,
            "小雨": 0.65,
            "中雨": 0.85,
        }[condition]
        return GetWeatherOutput(
            condition=condition,
            temperature_range=TemperatureRange(
                min_celsius=float(base), max_celsius=float(base + 6)
            ),
            precipitation_probability=precipitation,
            source=SourceType.MOCK,
            is_forecast=True,
            collected_at=fake_data.COLLECTED_AT,
        )


# --- 内部工具 --------------------------------------------------------------


def _matches_query(query: str, destination: dict) -> bool:
    if not query:
        return True
    if destination["name"] in query:
        return True
    tags = {tag.upper() for tag in destination["experience_tags"]}
    keywords = {
        "FOOD": ["美食", "吃"],
        "CULTURE": ["人文", "文化", "历史", "博物馆"],
        "NATURE": ["自然", "风景", "山水", "公园"],
    }
    for tag in tags:
        if any(word in query for word in keywords.get(tag, [])):
            return True
    # 用户没有给出可识别偏好时，不做过早淘汰（推荐交给 LLM 比较）
    return not any(
        word for words in keywords.values() for word in words if word in query
    )


def _keyword_overlap(query: str, content: str) -> bool:
    tokens = [token for token in _tokenize(query) if len(token) >= 2]
    return any(token in content for token in tokens)


def _tokenize(text: str) -> list[str]:
    cleaned = text
    for ch in "，。、；：？！（）《》,.!?() \n":
        cleaned = cleaned.replace(ch, " ")
    return [token for token in cleaned.split(" ") if token]


def _destination_of(entity_id: str) -> str | None:
    if entity_id.startswith("dest_"):
        return entity_id
    resource = fake_data.find_resource(entity_id)
    return resource.destination_id if resource else None


def _entity_matches_type(entity_id: str, resource_type: ResourceType) -> bool:
    if entity_id.startswith("dest_"):
        return False
    resource = fake_data.find_resource(entity_id)
    return resource is not None and resource.resource_type is resource_type


def _distance_km(origin, destination) -> float:
    if origin is None or destination is None:
        return 5.0
    return _haversine(
        origin.latitude, origin.longitude, destination.latitude, destination.longitude
    )


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    # 城市内部路线通常比直线距离长 20%–35%
    return round(2 * radius * math.asin(math.sqrt(a)) * 1.3, 2)


def is_mock_only(output: object) -> bool:
    """判断 MCP 输出是否只含模拟数据，供上层决定是否标注降级。"""

    evidence = getattr(output, "evidence", None)
    if evidence is None:
        return False
    return all(e.acquisition_status is AcquisitionStatus.MOCK_ONLY for e in evidence)
