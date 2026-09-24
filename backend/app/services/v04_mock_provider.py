"""v0.4 契约版的模拟数据 + MCP 工具实现。

本模块取代了 v0.3 的 `travel_mcp_client.py` + `fake_data.py`（两者已删除），
供 v0.4 的图、C3 前置过滤与 C4 规划使用。数据全部 MOCK_ONLY。

A 线接入真实 MCP Server 后，只需替换本模块的 Provider 实现，
上层节点与过滤逻辑不变。
"""

from __future__ import annotations

from datetime import date, datetime

from app.schemas import (
    DataSnapshot,
    DestinationCoverageSnapshot,
    DestinationRecommendation,
    Evidence,
    Money,
    PlanningReadinessEvaluation,
    ReadinessTripContext,
    ResourceCandidateUnion,
    RestaurantCandidate,
    RunMode,
    TimeWindow,
    TripProfile,
    VisitPlaceCandidate,
)
from app.schemas.v04.mcp import (
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

_NOW = datetime.fromisoformat("2026-09-24T10:00:00+08:00")
_COVERAGE_VERSION = "2026-09-23-v1"


def at(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """构造模拟时间点（v0.4 的 `TimeWindow` 用 `start_at` / `end_at`，都是 datetime）。"""

    return _NOW.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)


_MORNING = [TimeWindow(start_at=at(9), end_at=at(17))]

#: 模拟目的地：名称、覆盖快照、可提供的能力。
DESTINATIONS: dict[str, dict] = {
    "dest_chengdu": {
        "name": "成都",
        "experience_tags": ["FOOD", "CULTURE", "NIGHTLIFE", "SHOPPING"],
        "recommended_min_days": 2,
        "recommended_max_days": 5,
        "category_status": {
            "DESTINATION_PROFILE": "MOCK_ONLY",
            "VISIT_PLACE": "MOCK_ONLY",
            "OPENING_RULE": "MOCK_ONLY",
            "ROUTE": "MOCK_ONLY",
            "LODGING": "MOCK_ONLY",
        },
        "visit_place_count": 12,
    },
    "dest_leshan": {
        "name": "乐山",
        "experience_tags": ["FOOD", "CULTURE", "NATURE"],
        "recommended_min_days": 1,
        "recommended_max_days": 2,
        "category_status": {
            "DESTINATION_PROFILE": "MOCK_ONLY",
            "VISIT_PLACE": "MOCK_ONLY",
            "OPENING_RULE": "LIMITED",
            "ROUTE": "LIMITED",
            "LODGING": "LIMITED",
        },
        "visit_place_count": 6,
    },
    "dest_dujiangyan": {
        "name": "都江堰",
        "experience_tags": ["NATURE", "CULTURE"],
        "recommended_min_days": 1,
        "recommended_max_days": 2,
        "category_status": {
            "DESTINATION_PROFILE": "MOCK_ONLY",
            "VISIT_PLACE": "LIMITED",
            "OPENING_RULE": "UNAVAILABLE",
            "ROUTE": "UNASSESSED",
            "LODGING": "UNASSESSED",
        },
        "visit_place_count": 2,
    },
}


def destination_name(destination_id: str) -> str | None:
    """目的地 ID → 中文名；未收录时返回 None，由调用方决定如何降级。"""

    meta = DESTINATIONS.get(destination_id)
    return meta["name"] if meta else None


def known_destinations() -> dict[str, str]:
    """“目的地名称 → ID”映射，供自然语言解析器识别用户点名的目的地。

    ⚠️ 现阶段来自 C 线模拟数据；A 线接入 MySQL 后应改为从
    `search_planning_ready_destinations` 的别名索引获取，这里是替换点。
    """

    return {meta["name"]: destination_id for destination_id, meta in DESTINATIONS.items()}


def coverage_snapshot(destination_id: str) -> DestinationCoverageSnapshot:
    meta = DESTINATIONS[destination_id]
    return DestinationCoverageSnapshot(
        coverage_snapshot_id=f"cov_{destination_id}",
        destination_id=destination_id,
        coverage_version=_COVERAGE_VERSION,
        category_status=meta["category_status"],
        missing_capabilities=["REALTIME_HOTEL_AVAILABILITY"],
        evaluated_at=_NOW,
    )


def readiness_evaluation(
    destination_id: str, profile: TripProfile
) -> PlanningReadinessEvaluation:
    """按**本次旅行**重算就绪度（`CONTRACTS.md` §3.2）。

    规则：每天至少 2 个游玩地点并保留 1 个替代项；
    开放规则与路线数据必须达到 LIMITED 以上。
    """

    meta = DESTINATIONS[destination_id]
    status = meta["category_status"]
    required = profile.duration_days * 2 + 1
    failed: list[str] = []
    if meta["visit_place_count"] < required:
        failed.append("VISIT_PLACE_COVERAGE")
    for capability in ("OPENING_RULE", "ROUTE", "LODGING"):
        # LIMITED 表示“有数据但覆盖有限”，可以规划；UNAVAILABLE / UNASSESSED 不允许
        if status.get(capability) in ("UNAVAILABLE", "UNASSESSED"):
            failed.append(f"{capability}_COVERAGE")
    return PlanningReadinessEvaluation(
        readiness_id=f"ready_{destination_id}_{profile.profile_version}",
        destination_id=destination_id,
        trip_profile_version=profile.profile_version,
        evaluated_for=ReadinessTripContext(
            start_date=profile.start_date,
            end_date=profile.end_date,
            duration_days=profile.duration_days,
            traveler_count=profile.traveler_count,
        ),
        required_capabilities=["DESTINATION_PROFILE", "VISIT_PLACE", "OPENING_RULE", "ROUTE", "LODGING"],
        failed_requirements=failed,
        coverage_snapshot_id=f"cov_{destination_id}",
        ruleset_version="rules-2026-09-24-v1",
        planning_ready=not failed,
        evaluated_at=_NOW,
    )


EVIDENCE: list[Evidence] = [
    Evidence(
        evidence_id="ev_101",
        entity_id="dest_chengdu",
        entity_type="DESTINATION",
        content="成都适合慢节奏城市漫步与美食体验，坑点集中在少数片区，跨区通勤可控。",
        source_type="MOCK",
        source_ref="mock://dest_chengdu",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "FOOD"],
    ),
    Evidence(
        evidence_id="ev_301",
        entity_id="poi_1001",
        entity_type="VISIT_PLACE",
        content="该博物馆以本地历史文化展陈为主，室内为主，适合雨天与上午时段。",
        source_type="MOCK",
        source_ref="mock://poi_1001",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "INDOOR"],
    ),
]

#: 模拟资源候选。`poi_1002` 为闭馆资源，用于验证前置过滤与闭馆替换。
VISIT_PLACES: list[VisitPlaceCandidate] = [
    VisitPlaceCandidate(
        resource_id="poi_1001",
        destination_id="dest_chengdu",
        area_id="area_001",
        name="示例历史博物馆",
        address="示例地址 1 号",
        latitude=30.6595,
        longitude=104.0633,
        categories=["CULTURE", "INDOOR"],
        suggested_duration_minutes=120,
        availability_status="AVAILABLE",
        opening_windows=_MORNING,
        physical_intensity="LOW",
        indoor=True,
        weather_sensitivity="LOW",
        planning_fact_ids=["pf_poi_1001"],
        evidence_ids=["ev_301"],
    ),
    VisitPlaceCandidate(
        resource_id="poi_1002",
        destination_id="dest_chengdu",
        area_id="area_001",
        name="示例美术馆",
        address="示例地址 2 号",
        latitude=30.6650,
        longitude=104.0700,
        categories=["CULTURE", "INDOOR"],
        suggested_duration_minutes=90,
        availability_status="UNAVAILABLE",
        opening_windows=[],
        physical_intensity="LOW",
        indoor=True,
        weather_sensitivity="LOW",
        planning_fact_ids=["pf_poi_1002"],
        evidence_ids=["ev_301"],
    ),
    VisitPlaceCandidate(
        resource_id="poi_1003",
        destination_id="dest_chengdu",
        area_id="area_002",
        name="示例历史街区",
        address="示例地址 3 号",
        latitude=30.6460,
        longitude=104.0550,
        categories=["CULTURE", "OUTDOOR", "FOOD"],
        suggested_duration_minutes=120,
        availability_status="AVAILABLE",
        opening_windows=[TimeWindow(start_at=at(13, 30), end_at=at(21, 30))],
        physical_intensity="LOW",
        indoor=False,
        weather_sensitivity="MEDIUM",
        planning_fact_ids=["pf_poi_1003"],
        evidence_ids=["ev_301"],
    ),
]

RESTAURANTS: list[RestaurantCandidate] = [
    RestaurantCandidate(
        resource_id="rest_2001",
        destination_id="dest_chengdu",
        area_id="area_002",
        name="示例本地餐厅",
        address="示例地址 4 号",
        latitude=30.6480,
        longitude=104.0560,
        cuisine="川菜",
        specialty_dishes=["示例招牌菜"],
        price_per_person=Money(amount=80, currency="CNY"),
        opening_windows=[TimeWindow(start_at=at(11), end_at=at(21))],
        meal_types=["LUNCH", "DINNER"],
        dietary_tags=["辣"],
        route_fit_reason="与历史街区步行 5 分钟",
        planning_fact_ids=["pf_rest_2001"],
        evidence_ids=["ev_301"],
    )
]

#: 闭馆日期（模拟）：这些日期上 `poi_1002` 明确不可用。
CLOSED_DATES: dict[str, set[date]] = {
    "poi_1002": {date(2026, 10, d) for d in range(3, 7)},
}


class V04MockMCPProvider:
    """9 个 MCP 工具的 v0.4 实现（全部返回 MOCK_ONLY 数据）。"""

    #: 供上层判断“当前数据是不是模拟数据”（前端必须显式告知）
    is_mock_only = True

    def search_planning_ready_destinations(
        self, request: SearchPlanningReadyDestinationsRequest
    ) -> SearchPlanningReadyDestinationsResponse:
        profile = request.trip_profile
        readiness: list[PlanningReadinessEvaluation] = []
        recommendations: list[DestinationRecommendation] = []
        for destination_id in DESTINATIONS:
            evaluation = readiness_evaluation(destination_id, profile)
            readiness.append(evaluation)
            if not evaluation.planning_ready:
                continue
            recommendations.append(
                DestinationRecommendation(
                    destination_id=destination_id,
                    readiness_id=evaluation.readiness_id,
                    suggested_days=min(
                        profile.duration_days,
                        max(1, DESTINATIONS[destination_id]["visit_place_count"] // 3),
                    ),
                    reason=f"{DESTINATIONS[destination_id]['name']}覆盖达标（{_COVERAGE_VERSION}）",
                    evidence_ids=["ev_101"],
                )
            )
        return SearchPlanningReadyDestinationsResponse(
            recommendations=recommendations[: request.top_k],
            readiness_evaluations=readiness,
        )

    def search_travel_knowledge(
        self, request: SearchTravelKnowledgeRequest
    ) -> SearchTravelKnowledgeResponse:
        items = list(EVIDENCE)
        if request.destination_ids:
            allowed = set(request.destination_ids)
            items = [
                item
                for item in items
                if item.entity_id in allowed or item.entity_id.startswith("poi_")
            ]
        if request.entity_types:
            types = set(request.entity_types)
            items = [item for item in items if item.entity_type in types]
        return SearchTravelKnowledgeResponse(evidence=items[: request.top_k])

    def search_resources(
        self, request: SearchResourcesRequest
    ) -> SearchResourcesResponse:
        resources: list[ResourceCandidateUnion] = []
        if request.resource_type == "VISIT_PLACE":
            resources = [
                item for item in VISIT_PLACES if item.destination_id == request.destination_id
            ]
        elif request.resource_type == "RESTAURANT":
            resources = [
                item for item in RESTAURANTS if item.destination_id == request.destination_id
            ]
        return SearchResourcesResponse(resources=resources)

    def get_resource_availability(
        self, request: GetResourceAvailabilityRequest
    ) -> GetResourceAvailabilityResponse:
        for item in [*VISIT_PLACES, *RESTAURANTS]:
            if item.resource_id != request.resource_id:
                continue
            if request.date in CLOSED_DATES.get(item.resource_id, set()):
                return GetResourceAvailabilityResponse(
                    status="UNAVAILABLE",
                    reason=f"{request.date.isoformat()} 闭馆维护（模拟）",
                    planning_fact_ids=item.planning_fact_ids,
                )
            return GetResourceAvailabilityResponse(
                status=item.availability_status,
                available_windows=item.opening_windows,
                reservation_required=False,
                reason=None,
                planning_fact_ids=item.planning_fact_ids,
            )
        return GetResourceAvailabilityResponse(
            status="UNKNOWN", reason=f"未收录资源 {request.resource_id}"
        )

    def get_resource_facts(
        self, request: GetResourceFactsRequest
    ) -> GetResourceFactsResponse:
        return GetResourceFactsResponse()

    def get_intercity_options(
        self, request: GetIntercityOptionsRequest
    ) -> GetIntercityOptionsResponse:  # pragma: no cover - P1
        raise NotImplementedError("城际交通为 P1，尚未提供模拟实现")

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse:
        return GetRouteResponse(
            routes=[
                RouteOption(
                    mode="METRO",
                    duration_minutes=25,
                    distance_km=6.4,
                    estimated_cost=Money(amount=4, currency="CNY"),
                    walking_minutes=8,
                    transfer_count=1,
                    source="MOCK",
                    is_estimated=True,
                )
            ]
        )

    def get_weather(self, request: GetWeatherRequest) -> GetWeatherResponse:
        days: list[WeatherFact] = []
        current = request.date_range.start_date
        while current <= request.date_range.end_date:
            days.append(
                WeatherFact(
                    date=current,
                    condition="多云",
                    temperature_min_celsius=16.0,
                    temperature_max_celsius=22.0,
                    precipitation_probability=0.3,
                    source="MOCK",
                    is_forecast=True,
                    data_assurance_status="MOCK",
                )
            )
            current = current.fromordinal(current.toordinal() + 1)
        return GetWeatherResponse(weather_facts=days)

    def get_preparation_rules(
        self, request: GetPreparationRulesRequest
    ) -> GetPreparationRulesResponse:
        return GetPreparationRulesResponse()


def build_data_snapshot(profile: TripProfile) -> DataSnapshot:
    """记录本次规划使用的数据版本（`CONTRACTS.md` §4.4）。"""

    return DataSnapshot(
        data_snapshot_id="snap_mock_001",
        created_at=_NOW,
        run_mode=RunMode.DEMO,
        trip_profile_version=profile.profile_version,
        readiness_evaluation_ids=[],
        planning_fact_ids=[],
        evidence_ids=[item.evidence_id for item in EVIDENCE],
        provider_versions=["mock-provider-2026-09-24"],
        ruleset_versions=["rules-2026-09-24-v1"],
        expired_items=[],
        degraded_items=[],
        mock_items=[item.evidence_id for item in EVIDENCE],
        unknown_items=["REALTIME_HOTEL_AVAILABILITY"],
    )


def travel_date_range(start: date, end: date) -> DateRange:
    return DateRange(start_date=start, end_date=end)
