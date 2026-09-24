"""A-line mock Provider implementing all nine v0.4 MCP contracts.

The data is deliberately small and marked MOCK/MOCK_ONLY.  This module keeps
the original ``V04MockMCPProvider`` import path so C's graph and dependency
injection continue to work while A later swaps in Snapshot/Live providers.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.schemas import (
    DataSnapshot,
    DestinationCoverageSnapshot,
    DestinationRecommendation,
    Evidence,
    FactRecord,
    IntercityOption,
    Money,
    PlanningFact,
    PlanningReadinessEvaluation,
    PreparationRule,
    ReadinessTripContext,
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


_TZ = timezone(timedelta(hours=8))
_NOW = datetime(2026, 9, 24, 10, 0, tzinfo=_TZ)
_COVERAGE_VERSION = "2026-09-24-mock-v2"


class DataMissingError(RuntimeError):
    """Provider cannot cover the requested scope without inventing data."""

    code = "DATA_MISSING"

    def __init__(self, message: str, *, missing_dates: list[date] | None = None):
        super().__init__(message)
        self.missing_dates = tuple(missing_dates or [])


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=_TZ)


def _window(day: date, start: tuple[int, int], end: tuple[int, int]) -> TimeWindow:
    return TimeWindow(
        start_at=_at(day, *start),
        end_at=_at(day, *end),
    )


def _trip_dates(date_range: DateRange) -> list[date]:
    span = (date_range.end_date - date_range.start_date).days
    return [date_range.start_date + timedelta(days=offset) for offset in range(span + 1)]


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
    meta = DESTINATIONS.get(destination_id)
    return meta["name"] if meta else None


def known_destinations() -> dict[str, str]:
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
    meta = DESTINATIONS[destination_id]
    status = meta["category_status"]
    required = profile.duration_days * 2 + 1
    failed: list[str] = []
    if meta["visit_place_count"] < required:
        failed.append("VISIT_PLACE_COVERAGE")
    for capability in ("OPENING_RULE", "ROUTE", "LODGING"):
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
        required_capabilities=[
            "DESTINATION_PROFILE",
            "VISIT_PLACE",
            "OPENING_RULE",
            "ROUTE",
            "LODGING",
        ],
        failed_requirements=failed,
        coverage_snapshot_id=f"cov_{destination_id}",
        ruleset_version="mock-rules-2026-09-24-v2",
        planning_ready=not failed,
        evaluated_at=_NOW,
    )


EVIDENCE_DESTINATION: dict[str, str] = {
    "ev_101": "dest_chengdu",
    "ev_301": "dest_chengdu",
}

EVIDENCE: list[Evidence] = [
    Evidence(
        evidence_id="ev_101",
        entity_id="dest_chengdu",
        entity_type="DESTINATION",
        content="成都适合慢节奏城市漫步与美食体验，核心体验集中在少数片区。",
        source_type="MOCK",
        source_ref="mock://dest_chengdu",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "FOOD", "RELAXED"],
    ),
    Evidence(
        evidence_id="ev_301",
        entity_id="poi_1001",
        entity_type="VISIT_PLACE",
        content="示例历史博物馆以本地文化展陈为主，室内为主，适合雨天与上午。",
        source_type="MOCK",
        source_ref="mock://poi_1001",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "INDOOR", "MUSEUM"],
    ),
]


RESOURCE_META: dict[str, dict] = {
    "poi_1001": {
        "destination_id": "dest_chengdu",
        "area_id": "area_001",
        "name": "示例历史博物馆",
        "address": "示例地址 1 号",
        "latitude": 30.6595,
        "longitude": 104.0633,
        "categories": ["CULTURE", "INDOOR"],
        "duration": 120,
        "hours": ((9, 0), (17, 0)),
        "last_entry": (16, 30),
        "physical_intensity": "LOW",
        "indoor": True,
        "weather_sensitivity": "LOW",
        "fact_ids": ["pf_poi_1001_open", "pf_poi_1001_price"],
        "evidence_ids": ["ev_301"],
    },
    "poi_1002": {
        "destination_id": "dest_chengdu",
        "area_id": "area_001",
        "name": "示例美术馆",
        "address": "示例地址 2 号",
        "latitude": 30.6650,
        "longitude": 104.0700,
        "categories": ["CULTURE", "INDOOR"],
        "duration": 90,
        "hours": ((9, 0), (17, 0)),
        "last_entry": (16, 30),
        "physical_intensity": "LOW",
        "indoor": True,
        "weather_sensitivity": "LOW",
        "fact_ids": ["pf_poi_1002_open"],
        "evidence_ids": ["ev_301"],
    },
    "poi_1003": {
        "destination_id": "dest_chengdu",
        "area_id": "area_002",
        "name": "示例历史街区",
        "address": "示例地址 3 号",
        "latitude": 30.6460,
        "longitude": 104.0550,
        "categories": ["CULTURE", "OUTDOOR", "FOOD"],
        "duration": 120,
        "hours": ((13, 30), (21, 30)),
        "last_entry": None,
        "physical_intensity": "LOW",
        "indoor": False,
        "weather_sensitivity": "MEDIUM",
        "fact_ids": ["pf_poi_1003_open"],
        "evidence_ids": ["ev_301"],
    },
}

RESTAURANT_META: dict[str, dict] = {
    "rest_2001": {
        "destination_id": "dest_chengdu",
        "area_id": "area_002",
        "name": "示例本地餐厅",
        "address": "示例地址 4 号",
        "latitude": 30.6480,
        "longitude": 104.0560,
        "hours": ((11, 0), (21, 0)),
        "fact_ids": ["pf_rest_2001_open"],
    }
}

CLOSED_DATES: dict[str, set[date]] = {
    "poi_1002": {date(2026, 10, day) for day in range(2, 7)},
}


def _visit_place(resource_id: str, date_range: DateRange) -> VisitPlaceCandidate:
    meta = RESOURCE_META[resource_id]
    dates = _trip_dates(date_range)
    windows = [
        _window(day, meta["hours"][0], meta["hours"][1])
        for day in dates
        if day not in CLOSED_DATES.get(resource_id, set())
    ]
    first_day = dates[0]
    last_entry = (
        _at(first_day, *meta["last_entry"]) if meta["last_entry"] else None
    )
    status = "AVAILABLE" if windows else "UNAVAILABLE"
    return VisitPlaceCandidate(
        resource_id=resource_id,
        destination_id=meta["destination_id"],
        area_id=meta["area_id"],
        name=meta["name"],
        address=meta["address"],
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        categories=meta["categories"],
        suggested_duration_minutes=meta["duration"],
        availability_status=status,
        opening_windows=windows,
        last_entry_at=last_entry,
        physical_intensity=meta["physical_intensity"],
        indoor=meta["indoor"],
        weather_sensitivity=meta["weather_sensitivity"],
        planning_fact_ids=meta["fact_ids"],
        evidence_ids=meta["evidence_ids"],
    )


def _restaurant(resource_id: str, date_range: DateRange) -> RestaurantCandidate:
    meta = RESTAURANT_META[resource_id]
    return RestaurantCandidate(
        resource_id=resource_id,
        destination_id=meta["destination_id"],
        area_id=meta["area_id"],
        name=meta["name"],
        address=meta["address"],
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        cuisine="川菜",
        specialty_dishes=["示例招牌菜"],
        price_per_person=Money(amount=80, currency="CNY"),
        opening_windows=[
            _window(day, meta["hours"][0], meta["hours"][1])
            for day in _trip_dates(date_range)
        ],
        meal_types=["LUNCH", "DINNER"],
        dietary_tags=["SPICY"],
        route_fit_reason="与示例历史街区步行约 5 分钟",
        planning_fact_ids=meta["fact_ids"],
        evidence_ids=["ev_301"],
    )


FACT_RECORDS: list[FactRecord] = [
    FactRecord(
        fact_record_id="fact_poi_1001_open",
        entity_id="poi_1001",
        fact_type="OPENING_HOURS",
        value={"open": "09:00", "last_entry": "16:30", "close": "17:00"},
        source_type="MOCK",
        source_ref="mock://poi_1001/opening",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    ),
    FactRecord(
        fact_record_id="fact_poi_1001_price",
        entity_id="poi_1001",
        fact_type="TICKET_PRICE",
        value={"amount": 50, "currency": "CNY"},
        source_type="MOCK",
        source_ref="mock://poi_1001/price",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    ),
]

PLANNING_FACTS: list[PlanningFact] = [
    PlanningFact(
        planning_fact_id="pf_poi_1001_open",
        fact_record_id="fact_poi_1001_open",
        entity_id="poi_1001",
        fact_type="OPENING_HOURS",
        normalized_value={"open": "09:00", "last_entry": "16:30", "close": "17:00"},
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    ),
    PlanningFact(
        planning_fact_id="pf_poi_1001_price",
        fact_record_id="fact_poi_1001_price",
        entity_id="poi_1001",
        fact_type="TICKET_PRICE",
        normalized_value={"amount": 50, "currency": "CNY"},
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    ),
]

INTERCITY_OPTIONS: dict[tuple[str, str, date], list[IntercityOption]] = {
    ("上海", "dest_chengdu", date(2026, 10, 2)): [
        IntercityOption(
            option_id="intercity_shanghai_chengdu_20261002",
            mode="HIGH_SPEED_RAIL",
            origin_station="上海示例站",
            destination_station="成都示例站",
            departure_window=_window(date(2026, 10, 2), (8, 0), (8, 30)),
            arrival_window=_window(date(2026, 10, 2), (11, 0), (11, 30)),
            door_to_door_minutes=240,
            price_range=Money(min_amount=200, max_amount=300, currency="CNY"),
            booking_required=True,
            booking_advice="Mock 数据：建议提前购票",
            risk_flags=["MOCK_DATA"],
        )
    ]
}

ROUTES: dict[tuple[str, str], list[RouteOption]] = {
    ("poi_1001", "poi_1003"): [
        RouteOption(
            mode="METRO",
            duration_minutes=25,
            distance_km=6.4,
            estimated_cost=Money(amount=4, currency="CNY"),
            walking_minutes=8,
            transfer_count=1,
            congestion_level="LOW",
            source="MOCK",
            is_estimated=True,
        )
    ],
    ("poi_1003", "rest_2001"): [
        RouteOption(
            mode="WALK",
            duration_minutes=5,
            distance_km=0.4,
            estimated_cost=Money(amount=0, currency="CNY"),
            walking_minutes=5,
            transfer_count=0,
            congestion_level="LOW",
            source="MOCK",
            is_estimated=True,
        )
    ],
}

WEATHER: dict[tuple[str, date], WeatherFact] = {
    ("dest_chengdu", date(2026, 10, 2)): WeatherFact(
        date=date(2026, 10, 2),
        condition="多云",
        temperature_min_celsius=16,
        temperature_max_celsius=24,
        precipitation_probability=0.2,
        source="MOCK",
        data_assurance_status="MOCK",
    ),
    ("dest_chengdu", date(2026, 10, 3)): WeatherFact(
        date=date(2026, 10, 3),
        condition="小雨",
        temperature_min_celsius=15,
        temperature_max_celsius=21,
        precipitation_probability=0.75,
        source="MOCK",
        data_assurance_status="MOCK",
    ),
    ("dest_chengdu", date(2026, 10, 4)): WeatherFact(
        date=date(2026, 10, 4),
        condition="阴",
        temperature_min_celsius=15,
        temperature_max_celsius=22,
        precipitation_probability=0.35,
        source="MOCK",
        data_assurance_status="MOCK",
    ),
}

PREPARATION_RULES: list[PreparationRule] = [
    PreparationRule(
        rule_id="prep_identity",
        trigger_type="TRAVELER",
        trigger_condition={"always": True},
        category="DOCUMENT",
        item_name="身份证件",
        instruction="携带乘车和预约所需的有效身份证件。",
        priority="REQUIRED",
        reason="实名交通和预约项目需要核验",
    ),
    PreparationRule(
        rule_id="prep_rain",
        trigger_type="WEATHER",
        trigger_condition={"precipitation_probability_gte": 0.5},
        category="EQUIPMENT",
        item_name="雨具",
        instruction="准备折叠伞和防滑鞋，并在出发前刷新天气。",
        priority="RECOMMENDED",
        reason="天气数据包含较高降水概率",
    ),
    PreparationRule(
        rule_id="prep_outdoor",
        trigger_type="ACTIVITY",
        trigger_condition={"tags_any": ["OUTDOOR", "HIKING", "WATER_ACTIVITY"]},
        category="CLOTHING",
        item_name="户外防晒与舒适鞋",
        instruction="准备防晒用品和适合长时间行走的鞋。",
        priority="RECOMMENDED",
        reason="行程包含户外活动",
    ),
    PreparationRule(
        rule_id="prep_limited_walking",
        trigger_type="TRAVELER",
        trigger_condition={"mobility_constraints_any": ["LIMITED_WALKING", "WHEELCHAIR"]},
        category="HEALTH",
        item_name="体力与无障碍确认",
        instruction="确认无障碍入口、休息点和可减少步行的交通方式。",
        priority="REQUIRED",
        reason="同行者存在步行或行动限制",
    ),
]


class V04MockMCPProvider:
    """Nine-tool mock implementation using C's frozen request/response models."""

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
        allowed_destinations = set(request.destination_ids)
        entity_types = set(request.entity_types)
        query = request.query.casefold().strip()
        vocabulary = {
            "目的地",
            "体验",
            "特点",
            "美食",
            "文化",
            "历史",
            "博物馆",
            "室内",
            "自然",
            "雨天",
            "慢节奏",
        }
        terms = {term for term in vocabulary if term in query}
        terms.update(term.casefold() for term in request.query.split() if term.strip())
        scored: list[tuple[int, Evidence]] = []
        for item in EVIDENCE:
            if allowed_destinations and EVIDENCE_DESTINATION[item.evidence_id] not in allowed_destinations:
                continue
            if entity_types and item.entity_type not in entity_types:
                continue
            if not query:
                score = 1
            else:
                type_label = "目的地" if item.entity_type == "DESTINATION" else ""
                haystack = " ".join([item.content, *item.tags, type_label]).casefold()
                score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].collected_at), reverse=True)
        return SearchTravelKnowledgeResponse(
            evidence=[item for _, item in scored[: request.top_k]]
        )

    def search_resources(self, request: SearchResourcesRequest) -> SearchResourcesResponse:
        resources = []
        if request.resource_type == "VISIT_PLACE":
            resources = [
                _visit_place(resource_id, request.date_range)
                for resource_id, meta in RESOURCE_META.items()
                if meta["destination_id"] == request.destination_id
                and (not request.area_ids or meta["area_id"] in request.area_ids)
            ]
        elif request.resource_type == "RESTAURANT":
            resources = [
                _restaurant(resource_id, request.date_range)
                for resource_id, meta in RESTAURANT_META.items()
                if meta["destination_id"] == request.destination_id
                and (not request.area_ids or meta["area_id"] in request.area_ids)
            ]
        return SearchResourcesResponse(resources=resources)

    def get_resource_facts(self, request: GetResourceFactsRequest) -> GetResourceFactsResponse:
        resource_ids = set(request.resource_ids)
        fact_types = set(request.fact_types)
        facts = [
            item
            for item in FACT_RECORDS
            if item.entity_id in resource_ids
            and (not fact_types or item.fact_type in fact_types)
        ]
        fact_ids = {item.fact_record_id for item in facts}
        planning = [item for item in PLANNING_FACTS if item.fact_record_id in fact_ids]
        if request.date_range:
            planning = [
                item
                for item in planning
                if item.applies_to >= request.date_range.start_date
                and item.applies_from <= request.date_range.end_date
            ]
        return GetResourceFactsResponse(facts=facts, planning_facts=planning)

    def get_resource_availability(
        self, request: GetResourceAvailabilityRequest
    ) -> GetResourceAvailabilityResponse:
        meta = RESOURCE_META.get(request.resource_id)
        if meta:
            if request.date in CLOSED_DATES.get(request.resource_id, set()):
                return GetResourceAvailabilityResponse(
                    status="UNAVAILABLE",
                    reason=f"{request.date.isoformat()} 闭馆维护（模拟）",
                    planning_fact_ids=meta["fact_ids"],
                )
            entry_end = meta["last_entry"] or meta["hours"][1]
            entry_window = _window(request.date, meta["hours"][0], entry_end)
            if request.requested_window:
                requested = request.requested_window
                if requested.start_at < entry_window.start_at or requested.start_at > entry_window.end_at:
                    return GetResourceAvailabilityResponse(
                        status="UNAVAILABLE",
                        available_windows=[entry_window],
                        reason="请求开始时间不在当日允许进入窗口内",
                        planning_fact_ids=meta["fact_ids"],
                    )
            return GetResourceAvailabilityResponse(
                status="AVAILABLE",
                available_windows=[entry_window],
                planning_fact_ids=meta["fact_ids"],
            )
        restaurant = RESTAURANT_META.get(request.resource_id)
        if restaurant:
            return GetResourceAvailabilityResponse(
                status="AVAILABLE",
                available_windows=[
                    _window(request.date, restaurant["hours"][0], restaurant["hours"][1])
                ],
                planning_fact_ids=restaurant["fact_ids"],
            )
        return GetResourceAvailabilityResponse(
            status="UNKNOWN",
            reason=f"未收录资源 {request.resource_id}",
        )

    def get_intercity_options(
        self, request: GetIntercityOptionsRequest
    ) -> GetIntercityOptionsResponse:
        key = (
            request.origin_city,
            request.destination_id,
            request.arrival_or_departure_date,
        )
        return GetIntercityOptionsResponse(options=INTERCITY_OPTIONS.get(key, []))

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse:
        routes = ROUTES.get((request.origin, request.destination), [])
        if request.allowed_modes:
            allowed = {str(getattr(mode, "value", mode)) for mode in request.allowed_modes}
            routes = [route for route in routes if route.mode in allowed]
        return GetRouteResponse(routes=routes)

    def get_weather(self, request: GetWeatherRequest) -> GetWeatherResponse:
        if not request.destination_id:
            raise DataMissingError("Mock天气需要destination_id")
        dates = _trip_dates(request.date_range)
        facts = [
            WEATHER[(request.destination_id, day)]
            for day in dates
            if (request.destination_id, day) in WEATHER
        ]
        actual = {item.date for item in facts}
        missing = [day for day in dates if day not in actual]
        if missing:
            values = ", ".join(day.isoformat() for day in missing)
            raise DataMissingError(
                f"Mock天气缺少请求日期: {values}",
                missing_dates=missing,
            )
        return GetWeatherResponse(weather_facts=facts)

    def get_preparation_rules(
        self, request: GetPreparationRulesRequest
    ) -> GetPreparationRulesResponse:
        activity_tags = {tag.upper() for tag in request.activity_tags}
        mobility = {value.upper() for value in request.trip_profile.mobility_constraints}
        max_precipitation = max(
            (
                item.precipitation_probability or 0.0
                for item in request.weather_facts
            ),
            default=0.0,
        )
        matched: list[PreparationRule] = []
        for rule in PREPARATION_RULES:
            condition = rule.trigger_condition
            if rule.trigger_type == "WEATHER":
                applies = max_precipitation >= float(
                    condition.get("precipitation_probability_gte", 1.1)
                )
            elif rule.trigger_type == "ACTIVITY":
                required = {str(tag).upper() for tag in condition.get("tags_any", [])}
                applies = bool(activity_tags & required)
            elif rule.trigger_type == "TRAVELER":
                if condition.get("always") is True:
                    applies = True
                else:
                    required = {
                        str(value).upper()
                        for value in condition.get("mobility_constraints_any", [])
                    }
                    applies = bool(mobility & required)
            else:
                applies = False
            if applies:
                matched.append(rule)
        return GetPreparationRulesResponse(rules=matched)


def build_data_snapshot(profile: TripProfile) -> DataSnapshot:
    return DataSnapshot(
        data_snapshot_id="snap_mock_002",
        created_at=_NOW,
        run_mode=RunMode.DEMO,
        trip_profile_version=profile.profile_version,
        readiness_evaluation_ids=[],
        planning_fact_ids=[item.planning_fact_id for item in PLANNING_FACTS],
        evidence_ids=[item.evidence_id for item in EVIDENCE],
        provider_versions=["a-mock-provider-2026-09-24-v2"],
        ruleset_versions=["mock-rules-2026-09-24-v2"],
        expired_items=[],
        degraded_items=[],
        mock_items=[
            *[item.evidence_id for item in EVIDENCE],
            *[item.planning_fact_id for item in PLANNING_FACTS],
        ],
        unknown_items=["REALTIME_HOTEL_AVAILABILITY"],
    )


def travel_date_range(start: date, end: date) -> DateRange:
    return DateRange(start_date=start, end_date=end)

