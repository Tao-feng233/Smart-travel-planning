"""A-line mock Provider implementing all nine v0.4 MCP contracts.

The data is deliberately small and marked MOCK/MOCK_ONLY.  This module keeps
the original ``V04MockMCPProvider`` import path so C's graph and dependency
injection continue to work while A later swaps in Snapshot/Live providers.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import ceil, hypot

from app.schemas import (
    DataSnapshot,
    DestinationCoverageSnapshot,
    DestinationRecommendation,
    Evidence,
    FactRecord,
    IntercityOption,
    LodgingAreaCandidate,
    LodgingCandidate,
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
_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=_TZ)
_COVERAGE_VERSION = "2026-09-27-mock-v3"
_RULESET_VERSION = "rules-2026-09-27-v2"


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
    visit_place_count = sum(
        candidate.availability_status in ("AVAILABLE", "CONDITIONAL")
        for candidate in _visit_place_candidates(
            destination_id,
            DateRange(start_date=profile.start_date, end_date=profile.end_date),
        )
    )
    required = ceil(profile.duration_days * 1.5) + 1
    failed: list[str] = []
    if visit_place_count < required:
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
        ruleset_version=_RULESET_VERSION,
        planning_ready=not failed,
        evaluated_at=_NOW,
    )


EXTRA_VISIT_PLACE_SEEDS: list[dict] = [
    {
        "resource_id": "poi_1004",
        "name": "示例城市公园",
        "area_id": "area_001",
        "latitude": 30.6700,
        "longitude": 104.0580,
        "categories": ["NATURE", "OUTDOOR"],
        "duration": 90,
        "hours": ((8, 0), (20, 0)),
        "indoor": False,
    },
    {
        "resource_id": "poi_1005",
        "name": "示例非遗体验馆",
        "area_id": "area_001",
        "latitude": 30.6630,
        "longitude": 104.0610,
        "categories": ["CULTURE", "INDOOR"],
        "duration": 90,
        "hours": ((9, 30), (18, 0)),
        "indoor": True,
    },
    {
        "resource_id": "poi_1006",
        "name": "示例城市书店",
        "area_id": "area_001",
        "latitude": 30.6600,
        "longitude": 104.0730,
        "categories": ["CULTURE", "INDOOR", "RELAXED"],
        "duration": 60,
        "hours": ((10, 0), (21, 0)),
        "indoor": True,
    },
    {
        "resource_id": "poi_1007",
        "name": "示例传统街巷",
        "area_id": "area_002",
        "latitude": 30.6510,
        "longitude": 104.0520,
        "categories": ["CULTURE", "OUTDOOR"],
        "duration": 90,
        "hours": ((9, 0), (21, 0)),
        "indoor": False,
    },
    {
        "resource_id": "poi_1008",
        "name": "示例茶文化馆",
        "area_id": "area_002",
        "latitude": 30.6490,
        "longitude": 104.0600,
        "categories": ["FOOD", "CULTURE", "INDOOR"],
        "duration": 75,
        "hours": ((10, 0), (19, 0)),
        "indoor": True,
    },
    {
        "resource_id": "poi_1009",
        "name": "示例滨河步道",
        "area_id": "area_002",
        "latitude": 30.6420,
        "longitude": 104.0640,
        "categories": ["NATURE", "OUTDOOR", "RELAXED"],
        "duration": 75,
        "hours": ((7, 0), (22, 0)),
        "indoor": False,
    },
    {
        "resource_id": "poi_1010",
        "name": "示例科技体验馆",
        "area_id": "area_001",
        "latitude": 30.6750,
        "longitude": 104.0680,
        "categories": ["SCIENCE", "INDOOR"],
        "duration": 120,
        "hours": ((9, 0), (17, 30)),
        "indoor": True,
    },
    {
        "resource_id": "poi_1011",
        "name": "示例夜间市集",
        "area_id": "area_002",
        "latitude": 30.6470,
        "longitude": 104.0750,
        "categories": ["FOOD", "NIGHTLIFE", "OUTDOOR"],
        "duration": 90,
        "hours": ((17, 0), (22, 30)),
        "indoor": False,
    },
]


EVIDENCE_DESTINATION: dict[str, str] = {
    "ev_101": "dest_chengdu",
    "ev_301": "dest_chengdu",
    "ev_302": "dest_chengdu",
    "ev_303": "dest_chengdu",
    "ev_401": "dest_chengdu",
}
EVIDENCE_DESTINATION.update(
    {f"ev_{item['resource_id']}": "dest_chengdu" for item in EXTRA_VISIT_PLACE_SEEDS}
)

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
    Evidence(
        evidence_id="ev_302",
        entity_id="poi_1002",
        entity_type="VISIT_PLACE",
        content="示例美术馆是室内文化类 Mock 候选，适合低体力和雨天安排。",
        source_type="MOCK",
        source_ref="mock://poi_1002",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "INDOOR", "ART"],
    ),
    Evidence(
        evidence_id="ev_303",
        entity_id="poi_1003",
        entity_type="VISIT_PLACE",
        content="示例历史街区是室外文化与美食类 Mock 候选，雨天需要调整。",
        source_type="MOCK",
        source_ref="mock://poi_1003",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["CULTURE", "OUTDOOR", "FOOD"],
    ),
    Evidence(
        evidence_id="ev_401",
        entity_id="rest_2001",
        entity_type="RESTAURANT",
        content="示例本地餐厅是业务联调使用的 Mock 餐饮候选，不代表实时营业。",
        source_type="MOCK",
        source_ref="mock://rest_2001",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=["FOOD", "RESTAURANT"],
    ),
]

EVIDENCE.extend(
    Evidence(
        evidence_id=f"ev_{item['resource_id']}",
        entity_id=item["resource_id"],
        entity_type="VISIT_PLACE",
        content=f"{item['name']}是补足成都五日演示行程的 Mock 候选，不代表真实地点。",
        source_type="MOCK",
        source_ref=f"mock://{item['resource_id']}",
        collected_at=_NOW,
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
        tags=list(item["categories"]),
    )
    for item in EXTRA_VISIT_PLACE_SEEDS
)

EVIDENCE.extend(
    [
        Evidence(
            evidence_id="ev_lodging_area_001",
            entity_id="lodging_area_001",
            entity_type="LODGING_AREA",
            content="天府广场片区是演示住宿区域，方便衔接市中心活动与地铁出行。",
            source_type="MOCK",
            source_ref="mock://lodging_area_001",
            collected_at=_NOW,
            acquisition_status="MOCK_ONLY",
            verification_status="PENDING",
            tags=["LODGING", "CITY_CENTER", "METRO"],
        ),
        Evidence(
            evidence_id="ev_lodging_area_002",
            entity_id="lodging_area_002",
            entity_type="LODGING_AREA",
            content="春熙路片区是演示住宿区域，餐饮便利并适合城市游览。",
            source_type="MOCK",
            source_ref="mock://lodging_area_002",
            collected_at=_NOW,
            acquisition_status="MOCK_ONLY",
            verification_status="PENDING",
            tags=["LODGING", "FOOD", "METRO"],
        ),
        *[
            Evidence(
                evidence_id=f"ev_{resource_id}",
                entity_id=resource_id,
                entity_type="LODGING",
                content="该住宿仅为业务联调使用的演示候选，不代表实时可订。",
                source_type="MOCK",
                source_ref=f"mock://{resource_id}",
                collected_at=_NOW,
                acquisition_status="MOCK_ONLY",
                verification_status="PENDING",
                tags=["LODGING", "MOCK_ONLY"],
            )
            for resource_id in (
                "lodging_3001",
                "lodging_3002",
                "lodging_3003",
                "lodging_3004",
            )
        ],
    ]
)
EVIDENCE_DESTINATION.update(
    {
        item.evidence_id: "dest_chengdu"
        for item in EVIDENCE
        if item.evidence_id.startswith("ev_lodging")
    }
)


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
        "evidence_ids": ["ev_302"],
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
        "evidence_ids": ["ev_303"],
    },
}
RESOURCE_META.update(
    {
        item["resource_id"]: {
            "destination_id": "dest_chengdu",
            "area_id": item["area_id"],
            "name": item["name"],
            "address": f"{item['name']} Mock 地址",
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "categories": item["categories"],
            "duration": item["duration"],
            "hours": item["hours"],
            "last_entry": None,
            "physical_intensity": "LOW",
            "indoor": item["indoor"],
            "weather_sensitivity": "LOW" if item["indoor"] else "MEDIUM",
            "fact_ids": [f"pf_{item['resource_id']}_open"],
            "evidence_ids": [f"ev_{item['resource_id']}"],
        }
        for item in EXTRA_VISIT_PLACE_SEEDS
    }
)

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
        "evidence_ids": ["ev_401"],
    }
}

LODGING_AREA_META: dict[str, dict] = {
    "lodging_area_001": {
        "destination_id": "dest_chengdu",
        "name": "天府广场片区",
        "address": "成都市中心城区（演示）",
        "latitude": 30.6570,
        "longitude": 104.0668,
        "area_type": "CITY_CENTER",
        "nearby_transport": ["METRO_1", "METRO_2"],
        "food_convenience": "HIGH",
        "evidence_ids": ["ev_lodging_area_001"],
    },
    "lodging_area_002": {
        "destination_id": "dest_chengdu",
        "name": "春熙路片区",
        "address": "成都市锦江区（演示）",
        "latitude": 30.6544,
        "longitude": 104.0818,
        "area_type": "COMMERCIAL_CENTER",
        "nearby_transport": ["METRO_2", "METRO_3"],
        "food_convenience": "HIGH",
        "evidence_ids": ["ev_lodging_area_002"],
    },
}

LODGING_META: dict[str, dict] = {
    "lodging_3001": {
        "destination_id": "dest_chengdu",
        "area_id": "lodging_area_001",
        "name": "天府广场示例连锁酒店",
        "address": "天府广场片区示例地址 1",
        "latitude": 30.6576,
        "longitude": 104.0657,
        "lodging_type": "CHAIN",
        "lodging_area": "天府广场片区",
        "price_range": (320, 420),
        "rating": 4.6,
        "review_count": 860,
        "quality_flags": ["TRANSIT_FRIENDLY", "QUIET_ROOM_OPTION"],
        "facilities": ["ELEVATOR", "AIR_CONDITIONING", "LAUNDRY"],
        "commute_summary": "步行可达地铁站，前往两个演示活动片区约 15～25 分钟。",
        "suitable_for": ["FIRST_TIME_VISITOR", "NEAR_TRANSIT"],
    },
    "lodging_3002": {
        "destination_id": "dest_chengdu",
        "area_id": "lodging_area_001",
        "name": "天府广场示例经济酒店",
        "address": "天府广场片区示例地址 2",
        "latitude": 30.6559,
        "longitude": 104.0681,
        "lodging_type": "ECONOMY",
        "lodging_area": "天府广场片区",
        "price_range": (220, 300),
        "rating": 4.3,
        "review_count": 520,
        "quality_flags": ["BUDGET_FRIENDLY"],
        "facilities": ["ELEVATOR", "AIR_CONDITIONING"],
        "commute_summary": "靠近地铁换乘点，适合控制住宿预算的演示方案。",
        "suitable_for": ["BUDGET", "NEAR_TRANSIT"],
    },
    "lodging_3003": {
        "destination_id": "dest_chengdu",
        "area_id": "lodging_area_002",
        "name": "春熙路示例星级酒店",
        "address": "春熙路片区示例地址 1",
        "latitude": 30.6531,
        "longitude": 104.0805,
        "lodging_type": "STAR_HOTEL",
        "lodging_area": "春熙路片区",
        "price_range": (480, 680),
        "rating": 4.7,
        "review_count": 1260,
        "quality_flags": ["CENTRAL_LOCATION", "SERVICE"],
        "facilities": ["ELEVATOR", "BREAKFAST", "AIR_CONDITIONING", "GYM"],
        "commute_summary": "位于商业中心，餐饮方便，前往历史街区约 15 分钟。",
        "suitable_for": ["FOOD", "COMFORT"],
    },
    "lodging_3004": {
        "destination_id": "dest_chengdu",
        "area_id": "lodging_area_002",
        "name": "春熙路示例青年旅舍",
        "address": "春熙路片区示例地址 2",
        "latitude": 30.6550,
        "longitude": 104.0830,
        "lodging_type": "HOSTEL",
        "lodging_area": "春熙路片区",
        "price_range": (120, 220),
        "rating": 4.4,
        "review_count": 430,
        "quality_flags": ["BUDGET_FRIENDLY", "SOCIAL"],
        "facilities": ["AIR_CONDITIONING", "LAUNDRY", "LOCKER"],
        "commute_summary": "靠近餐饮与商业街，适合预算优先的演示方案。",
        "suitable_for": ["BUDGET", "SOLO_TRAVELER"],
    },
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


def _visit_place_candidates(
    destination_id: str,
    date_range: DateRange,
    area_ids: list[str] | None = None,
) -> list[VisitPlaceCandidate]:
    """Build the same real candidate set used by search and readiness checks."""

    selected_areas = set(area_ids or [])
    return [
        _visit_place(resource_id, date_range)
        for resource_id, meta in RESOURCE_META.items()
        if meta["destination_id"] == destination_id
        and (not selected_areas or meta["area_id"] in selected_areas)
    ]


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
        evidence_ids=meta["evidence_ids"],
    )


def _lodging_area(resource_id: str) -> LodgingAreaCandidate:
    meta = LODGING_AREA_META[resource_id]
    return LodgingAreaCandidate(
        resource_id=resource_id,
        area_id=resource_id,
        destination_id=meta["destination_id"],
        name=meta["name"],
        address=meta["address"],
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        categories=["LODGING_AREA"],
        availability_status="AVAILABLE",
        area_type=meta["area_type"],
        nearby_transport=meta["nearby_transport"],
        food_convenience=meta["food_convenience"],
        evidence_ids=meta["evidence_ids"],
    )


def _lodging(resource_id: str) -> LodgingCandidate:
    meta = LODGING_META[resource_id]
    return LodgingCandidate(
        resource_id=resource_id,
        destination_id=meta["destination_id"],
        area_id=meta["area_id"],
        name=meta["name"],
        address=meta["address"],
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        categories=["LODGING"],
        lodging_type=meta["lodging_type"],
        lodging_area=meta["lodging_area"],
        price_range=Money(
            min_amount=meta["price_range"][0],
            max_amount=meta["price_range"][1],
            currency="CNY",
        ),
        rating=meta["rating"],
        review_count=meta["review_count"],
        quality_flags=meta["quality_flags"],
        facilities=meta["facilities"],
        commute_summary=meta["commute_summary"],
        suitable_for=meta["suitable_for"],
        availability_status="CONDITIONAL",
        availability_is_realtime=False,
        evidence_ids=[f"ev_{resource_id}"],
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
    FactRecord(
        fact_record_id="fact_poi_1002_open",
        entity_id="poi_1002",
        fact_type="OPENING_HOURS",
        value={"open": "09:00", "last_entry": "16:30", "close": "17:00"},
        source_type="MOCK",
        source_ref="mock://poi_1002/opening",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    ),
    FactRecord(
        fact_record_id="fact_poi_1003_open",
        entity_id="poi_1003",
        fact_type="OPENING_HOURS",
        value={"open": "13:30", "close": "21:30"},
        source_type="MOCK",
        source_ref="mock://poi_1003/opening",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    ),
    FactRecord(
        fact_record_id="fact_rest_2001_open",
        entity_id="rest_2001",
        fact_type="OPENING_HOURS",
        value={"open": "11:00", "close": "21:00"},
        source_type="MOCK",
        source_ref="mock://rest_2001/opening",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    ),
]
FACT_RECORDS.extend(
    FactRecord(
        fact_record_id=f"fact_{item['resource_id']}_open",
        entity_id=item["resource_id"],
        fact_type="OPENING_HOURS",
        value={
            "open": f"{item['hours'][0][0]:02d}:{item['hours'][0][1]:02d}",
            "close": f"{item['hours'][1][0]:02d}:{item['hours'][1][1]:02d}",
        },
        source_type="MOCK",
        source_ref=f"mock://{item['resource_id']}/opening",
        collected_at=_NOW,
        valid_until=datetime(2026, 10, 31, 23, 59, tzinfo=_TZ),
        acquisition_status="MOCK_ONLY",
        verification_status="PENDING",
    )
    for item in EXTRA_VISIT_PLACE_SEEDS
)

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
    PlanningFact(
        planning_fact_id="pf_poi_1002_open",
        fact_record_id="fact_poi_1002_open",
        entity_id="poi_1002",
        fact_type="OPENING_HOURS",
        normalized_value={"open": "09:00", "last_entry": "16:30", "close": "17:00"},
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    ),
    PlanningFact(
        planning_fact_id="pf_poi_1003_open",
        fact_record_id="fact_poi_1003_open",
        entity_id="poi_1003",
        fact_type="OPENING_HOURS",
        normalized_value={"open": "13:30", "close": "21:30"},
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    ),
    PlanningFact(
        planning_fact_id="pf_rest_2001_open",
        fact_record_id="fact_rest_2001_open",
        entity_id="rest_2001",
        fact_type="OPENING_HOURS",
        normalized_value={"open": "11:00", "close": "21:00"},
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    ),
]
PLANNING_FACTS.extend(
    PlanningFact(
        planning_fact_id=f"pf_{item['resource_id']}_open",
        fact_record_id=f"fact_{item['resource_id']}_open",
        entity_id=item["resource_id"],
        fact_type="OPENING_HOURS",
        normalized_value={
            "open": f"{item['hours'][0][0]:02d}:{item['hours'][0][1]:02d}",
            "close": f"{item['hours'][1][0]:02d}:{item['hours'][1][1]:02d}",
        },
        applies_from=date(2026, 10, 1),
        applies_to=date(2026, 10, 31),
        assurance="MOCK",
    )
    for item in EXTRA_VISIT_PLACE_SEEDS
)

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

INTERCITY_OPTIONS[("dest_chengdu", "上海", date(2026, 10, 6))] = [
    IntercityOption(
        option_id="intercity_chengdu_shanghai_20261006",
        mode="HIGH_SPEED_RAIL",
        origin_station="成都东站",
        destination_station="上海虹桥站",
        departure_window=_window(date(2026, 10, 6), (15, 0), (15, 30)),
        arrival_window=_window(date(2026, 10, 6), (22, 30), (23, 0)),
        door_to_door_minutes=540,
        price_range=Money(min_amount=650, max_amount=850, currency="CNY"),
        booking_required=True,
        booking_advice="Mock 数据：返程方案仅用于业务联调，不代表真实车次或余票。",
        risk_flags=["MOCK_DATA", "NO_REALTIME_AVAILABILITY"],
    )
]

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


def _mock_route_between(
    origin: tuple[float, float], destination: tuple[float, float]
) -> list[RouteOption]:
    """Create a deterministic mock route for the small Chengdu demo matrix."""

    latitude_km = (origin[0] - destination[0]) * 111.0
    longitude_km = (origin[1] - destination[1]) * 96.0
    distance_km = max(0.2, round(hypot(latitude_km, longitude_km), 1))
    if distance_km <= 1.2:
        duration = max(5, round(distance_km / 4.5 * 60))
        return [
            RouteOption(
                mode="WALK",
                duration_minutes=duration,
                distance_km=distance_km,
                estimated_cost=Money(amount=0, currency="CNY"),
                walking_minutes=duration,
                transfer_count=0,
                congestion_level="LOW",
                source="MOCK",
                is_estimated=True,
            )
        ]
    duration = max(15, round(distance_km / 22 * 60) + 8)
    return [
        RouteOption(
            mode="METRO",
            duration_minutes=duration,
            distance_km=distance_km,
            estimated_cost=Money(amount=4, currency="CNY"),
            walking_minutes=8,
            transfer_count=1 if distance_km >= 5 else 0,
            congestion_level="LOW",
            source="MOCK",
            is_estimated=True,
        )
    ]


_LOCAL_ROUTE_POINTS: dict[str, tuple[float, float]] = {
    **{
        resource_id: (meta["latitude"], meta["longitude"])
        for resource_id, meta in RESOURCE_META.items()
    },
    **{
        resource_id: (meta["latitude"], meta["longitude"])
        for resource_id, meta in RESTAURANT_META.items()
    },
    **{
        resource_id: (meta["latitude"], meta["longitude"])
        for resource_id, meta in LODGING_META.items()
    },
    "成都东站": (30.6287, 104.1414),
    "成都示例站": (30.6287, 104.1414),
}
for _origin_id, _origin_coordinate in _LOCAL_ROUTE_POINTS.items():
    for _destination_id, _destination_coordinate in _LOCAL_ROUTE_POINTS.items():
        if _origin_id == _destination_id:
            continue
        ROUTES.setdefault(
            (_origin_id, _destination_id),
            _mock_route_between(_origin_coordinate, _destination_coordinate),
        )


def route_coordinate(point_id: str) -> tuple[float, float] | None:
    """把当前 Mock 资源/车站 ID 解析成 `(latitude, longitude)`。

    混合 Provider 在调用高德等真实地图 API 前用它做坐标解析；
    返回 `None` 表示不在当前成都 Mock 目录中，此时不得把资源 ID 当坐标发出。
    """

    return _LOCAL_ROUTE_POINTS.get(point_id)


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

WEATHER.update(
    {
        ("dest_chengdu", date(2026, 10, 5)): WeatherFact(
            date=date(2026, 10, 5),
            condition="多云",
            temperature_min_celsius=16,
            temperature_max_celsius=23,
            precipitation_probability=0.25,
            source="MOCK",
            data_assurance_status="MOCK",
        ),
        ("dest_chengdu", date(2026, 10, 6)): WeatherFact(
            date=date(2026, 10, 6),
            condition="阴",
            temperature_min_celsius=15,
            temperature_max_celsius=21,
            precipitation_probability=0.4,
            source="MOCK",
            data_assurance_status="MOCK",
        ),
    }
)

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
                    suggested_days=max(
                        DESTINATIONS[destination_id]["recommended_min_days"],
                        min(
                            profile.duration_days,
                            DESTINATIONS[destination_id]["recommended_max_days"],
                        ),
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
            resources = _visit_place_candidates(
                request.destination_id, request.date_range, request.area_ids
            )
        elif request.resource_type == "RESTAURANT":
            resources = [
                _restaurant(resource_id, request.date_range)
                for resource_id, meta in RESTAURANT_META.items()
                if meta["destination_id"] == request.destination_id
                and (not request.area_ids or meta["area_id"] in request.area_ids)
            ]
        elif request.resource_type == "LODGING":
            resources = [
                _lodging(resource_id)
                for resource_id, meta in LODGING_META.items()
                if meta["destination_id"] == request.destination_id
                and (not request.area_ids or meta["area_id"] in request.area_ids)
            ]
        elif request.resource_type == "LODGING_AREA":
            resources = [
                _lodging_area(resource_id)
                for resource_id, meta in LODGING_AREA_META.items()
                if meta["destination_id"] == request.destination_id
                and (not request.area_ids or resource_id in request.area_ids)
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
        if request.resource_id in LODGING_AREA_META:
            return GetResourceAvailabilityResponse(
                status="AVAILABLE",
                reason="Mock 住宿区域覆盖可用。",
            )
        if request.resource_id in LODGING_META:
            return GetResourceAvailabilityResponse(
                status="CONDITIONAL",
                reason="Mock 住宿候选没有实时库存，入住前必须再次确认。",
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
        data_snapshot_id="snap_mock_003",
        created_at=_NOW,
        run_mode=RunMode.DEMO,
        trip_profile_version=profile.profile_version,
        readiness_evaluation_ids=[],
        planning_fact_ids=[item.planning_fact_id for item in PLANNING_FACTS],
        evidence_ids=[item.evidence_id for item in EVIDENCE],
        provider_versions=["a-mock-provider-2026-09-27-v3"],
        ruleset_versions=[_RULESET_VERSION],
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

