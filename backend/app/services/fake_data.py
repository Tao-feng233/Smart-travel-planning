"""C 线自用的模拟数据（MOCK_ONLY）。

⚠️ 这里的数据**全部是模拟数据**，只用于 C 线在 A 线数据就绪前跑通流程。
所有 `Evidence` 都标记为 `source_type=MOCK` + `acquisition_status=MOCK_ONLY`，
前端与攻略必须显式标注为模拟，不得当作真实旅游事实展示
（`AGENTS.md`：不得把模拟数据当成真实数据）。

A 线完成 MySQL + Chroma + MCP Server 后，本文件的数据源应被真实 MCP 工具替换，
替换点见 `travel_mcp_client.FakeTravelMCPClient`。
"""

from __future__ import annotations

from datetime import datetime

from app.schemas import (
    AvailabilityStatus,
    EntityType,
    Evidence,
    KnowledgeCoverage,
    ResourceAvailability,
    ResourceCandidate,
    ResourceType,
    SourceType,
    TimeWindow,
    AcquisitionStatus,
    VerificationStatus,
)

_TZ = "+08:00"
COLLECTED_AT = datetime.fromisoformat(f"2026-09-20T10:00:00{_TZ}")
VALID_UNTIL = datetime.fromisoformat(f"2026-10-31T23:59:59{_TZ}")
COVERAGE_EVALUATED_AT = datetime.fromisoformat(f"2026-09-23T18:00:00{_TZ}")
COVERAGE_VERSION = "2026-09-23-v1"


def _coverage(
    destination_id: str,
    *,
    visit_place_count: int,
    planning_ready: bool,
    route_coverage: float = 0.8,
    lodging_coverage: float = 0.75,
    restaurant_coverage: float = 0.5,
    missing_capabilities: list[str] | None = None,
) -> KnowledgeCoverage:
    return KnowledgeCoverage(
        destination_id=destination_id,
        coverage_version=COVERAGE_VERSION,
        destination_profile_status=AcquisitionStatus.MOCK_ONLY,
        visit_place_count=visit_place_count,
        visit_place_fact_coverage=0.9 if planning_ready else 0.4,
        opening_rule_coverage=0.85 if planning_ready else 0.3,
        route_coverage=route_coverage,
        lodging_coverage=lodging_coverage,
        restaurant_coverage=restaurant_coverage,
        intercity_transport_coverage=0.6,
        preparation_rule_coverage=1.0,
        missing_capabilities=missing_capabilities or ["REALTIME_HOTEL_AVAILABILITY"],
        planning_ready=planning_ready,
        evaluated_at=COVERAGE_EVALUATED_AT,
    )


#: 模拟目的地。`dest_dujiangyan` 故意设为 planning_ready=false，
#: 用于验证“数据不足的目的地不会进入推荐”。
DESTINATIONS: list[dict] = [
    {
        "destination_id": "dest_chengdu",
        "name": "成都",
        "province": "四川省",
        "administrative_area": "四川省成都市",
        "destination_type": "CITY",
        "experience_tags": ["FOOD", "CULTURE", "NATURE"],
        "recommended_min_days": 2,
        "recommended_max_days": 5,
        "coverage": _coverage("dest_chengdu", visit_place_count=12, planning_ready=True),
    },
    {
        "destination_id": "dest_leshan",
        "name": "乐山",
        "province": "四川省",
        "administrative_area": "四川省乐山市",
        "destination_type": "CITY",
        "experience_tags": ["CULTURE", "FOOD"],
        "recommended_min_days": 1,
        "recommended_max_days": 2,
        "coverage": _coverage(
            "dest_leshan",
            visit_place_count=9,
            planning_ready=True,
            route_coverage=0.7,
            restaurant_coverage=0.4,
        ),
    },
    {
        "destination_id": "dest_dujiangyan",
        "name": "都江堰",
        "province": "四川省",
        "administrative_area": "四川省成都市都江堰市",
        "destination_type": "TOWN",
        "experience_tags": ["NATURE", "CULTURE"],
        "recommended_min_days": 1,
        "recommended_max_days": 2,
        "coverage": _coverage(
            "dest_dujiangyan",
            visit_place_count=4,
            planning_ready=False,
            route_coverage=0.2,
            lodging_coverage=0.2,
            restaurant_coverage=0.1,
            missing_capabilities=[
                "REALTIME_HOTEL_AVAILABILITY",
                "INSUFFICIENT_VISIT_PLACES",
                "INSUFFICIENT_ROUTE_DATA",
            ],
        ),
    },
]


def _evidence(
    evidence_id: str,
    entity_id: str,
    entity_type: EntityType,
    content: str,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        entity_id=entity_id,
        entity_type=entity_type,
        content=content,
        source_type=SourceType.MOCK,
        source_ref=f"mock://{entity_id}",
        collected_at=COLLECTED_AT,
        valid_until=None,
        acquisition_status=AcquisitionStatus.MOCK_ONLY,
        verification_status=VerificationStatus.PENDING,
    )


EVIDENCE: list[Evidence] = [
    _evidence(
        "ev_101",
        "dest_chengdu",
        EntityType.DESTINATION,
        "成都适合慢节奏的城市漫步与美食体验，核心景点集中在少数几个片区，"
        "跨区通勤时间可控；节假日主要商圈人流明显上升。",
    ),
    _evidence(
        "ev_102",
        "dest_leshan",
        EntityType.DESTINATION,
        "乐山以人文与本地饮食为特色，适合安排 1 至 2 天的短停留，"
        "与成都之间有城际高铁连接。",
    ),
    _evidence(
        "ev_103",
        "dest_dujiangyan",
        EntityType.DESTINATION,
        "都江堰自然与人文兼备，但当前可用数据覆盖不足，暂不进入完整攻略推荐。",
    ),
    _evidence(
        "ev_301",
        "poi_1001",
        EntityType.VISIT_PLACE,
        "该博物馆以本地历史文化展陈为主，室内为主，适合雨天与上午时段，"
        "建议预留约 2 小时。",
    ),
    _evidence(
        "ev_302",
        "poi_1003",
        EntityType.VISIT_PLACE,
        "该历史街区适合傍晚步行游览，餐饮选择集中，步行强度较低。",
    ),
]


def _visit_place(
    resource_id: str,
    name: str,
    *,
    categories: list[str],
    latitude: float,
    longitude: float,
    duration_minutes: int,
    cost: float | None,
    availability: ResourceAvailability,
    evidence_ids: list[str],
    intensity: str = "LOW",
    weather_sensitivity: str = "LOW",
) -> ResourceCandidate:
    return ResourceCandidate(
        resource_id=resource_id,
        resource_type=ResourceType.VISIT_PLACE,
        destination_id="dest_chengdu",
        name=name,
        latitude=latitude,
        longitude=longitude,
        categories=categories,
        suggested_duration_minutes=duration_minutes,
        estimated_cost=cost,
        availability=availability,
        physical_intensity=intensity,
        weather_sensitivity=weather_sensitivity,
        evidence_ids=evidence_ids,
        source_updated_at=COLLECTED_AT,
        valid_until=VALID_UNTIL,
    )


_MORNING_TO_EVENING = [TimeWindow(start="09:00", end="17:00")]
_LATE_AFTERNOON = [TimeWindow(start="13:30", end="21:30")]

#: 模拟游玩地点与餐厅。`poi_1002` 故意设为闭馆（UNAVAILABLE），
#: 用于验证 C3 前置过滤与 C5/C6 的“闭馆替换”修复链路。
RESOURCE_CANDIDATES: list[ResourceCandidate] = [
    _visit_place(
        "poi_1001",
        "示例历史博物馆",
        categories=["CULTURE", "INDOOR"],
        latitude=30.6595,
        longitude=104.0633,
        duration_minutes=120,
        cost=50,
        availability=ResourceAvailability(
            status=AvailabilityStatus.AVAILABLE,
            valid_dates=[],
            time_windows=_MORNING_TO_EVENING,
            reservation_required=False,
            reason=None,
        ),
        evidence_ids=["ev_301"],
    ),
    _visit_place(
        "poi_1002",
        "示例美术馆",
        categories=["CULTURE", "INDOOR"],
        latitude=30.6650,
        longitude=104.0700,
        duration_minutes=90,
        cost=0,
        availability=ResourceAvailability(
            status=AvailabilityStatus.UNAVAILABLE,
            valid_dates=[],
            time_windows=[],
            reservation_required=False,
            reason="2026-10-03 至 2026-10-06 闭馆维护（模拟）",
        ),
        evidence_ids=["ev_301"],
    ),
    _visit_place(
        "poi_1003",
        "示例历史街区",
        categories=["CULTURE", "OUTDOOR", "FOOD"],
        latitude=30.6460,
        longitude=104.0550,
        duration_minutes=120,
        cost=0,
        availability=ResourceAvailability(
            status=AvailabilityStatus.AVAILABLE,
            valid_dates=[],
            time_windows=_LATE_AFTERNOON,
            reservation_required=False,
            reason=None,
        ),
        evidence_ids=["ev_302"],
        weather_sensitivity="MEDIUM",
    ),
    _visit_place(
        "poi_1004",
        "示例城市公园",
        categories=["NATURE", "OUTDOOR"],
        latitude=30.6700,
        longitude=104.0450,
        duration_minutes=90,
        cost=0,
        availability=ResourceAvailability(
            status=AvailabilityStatus.CONDITIONAL,
            valid_dates=[],
            time_windows=_MORNING_TO_EVENING,
            reservation_required=False,
            reason="雨天体验明显下降，需确认天气后使用",
        ),
        evidence_ids=["ev_301"],
        weather_sensitivity="HIGH",
    ),
    ResourceCandidate(
        resource_id="rest_2001",
        resource_type=ResourceType.RESTAURANT,
        destination_id="dest_chengdu",
        name="示例本地餐厅",
        latitude=30.6480,
        longitude=104.0560,
        categories=["SICHUAN", "LUNCH", "DINNER"],
        suggested_duration_minutes=60,
        estimated_cost=80,
        availability=ResourceAvailability(
            status=AvailabilityStatus.CONDITIONAL,
            valid_dates=[],
            time_windows=[TimeWindow(start="11:00", end="14:00"), TimeWindow(start="17:00", end="21:00")],
            reservation_required=True,
            reason="节假日建议提前预约（模拟）",
        ),
        physical_intensity="LOW",
        weather_sensitivity="LOW",
        evidence_ids=["ev_302"],
        source_updated_at=COLLECTED_AT,
        valid_until=VALID_UNTIL,
    ),
]


def find_destination(destination_id: str) -> dict | None:
    return next(
        (d for d in DESTINATIONS if d["destination_id"] == destination_id), None
    )


def find_destination_by_name(name: str) -> dict | None:
    return next((d for d in DESTINATIONS if d["name"] == name), None)


def find_resource(resource_id: str) -> ResourceCandidate | None:
    return next(
        (r for r in RESOURCE_CANDIDATES if r.resource_id == resource_id), None
    )


def find_evidence(evidence_id: str) -> Evidence | None:
    return next((e for e in EVIDENCE if e.evidence_id == evidence_id), None)
