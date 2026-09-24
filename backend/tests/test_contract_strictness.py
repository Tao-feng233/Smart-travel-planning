"""契约约束测试。

对应 `AGENTS.md` 的协作检查项与 `CONTRACTS.md` 的硬性规则：
不得偷偷新增字段、不得把模拟数据当真实数据、不得让 REJECTED 证据流入、
不得让无原因的资源被标为不可用、不得让 LLM 绕过结构直接改契约。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.legacy import (
    Evidence,
    ItineraryPlan,
    ResourceCandidate,
    TravelGuide,
    TripProfile,
    UserAction,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_extra_top_level_field_is_rejected() -> None:
    raw = copy.deepcopy(load("trip_profile"))
    raw["favorite_color"] = "blue"
    with pytest.raises(ValidationError, match="favorite_color"):
        TripProfile.model_validate(raw)


def test_extra_nested_field_is_rejected() -> None:
    raw = copy.deepcopy(load("resource_candidates")[0])
    raw["availability"]["queue_minutes"] = 20
    with pytest.raises(ValidationError, match="queue_minutes"):
        ResourceCandidate.model_validate(raw)


def test_rejected_evidence_is_blocked() -> None:
    raw = copy.deepcopy(load("evidence")[0])
    raw["verification_status"] = "REJECTED"
    with pytest.raises(ValidationError, match="REJECTED"):
        Evidence.model_validate(raw)


def test_mock_source_must_be_marked_mock_only() -> None:
    raw = copy.deepcopy(load("evidence")[0])
    raw["source_type"] = "MOCK"
    raw["acquisition_status"] = "AVAILABLE"
    with pytest.raises(ValidationError, match="MOCK_ONLY"):
        Evidence.model_validate(raw)


def test_unknown_source_type_is_rejected() -> None:
    raw = copy.deepcopy(load("evidence")[0])
    raw["source_type"] = "BLOG_SUMMARY"
    with pytest.raises(ValidationError):
        Evidence.model_validate(raw)


def test_unavailable_resource_requires_reason() -> None:
    raw = copy.deepcopy(load("resource_candidates")[1])
    raw["availability"]["reason"] = None
    with pytest.raises(ValidationError, match="reason"):
        ResourceCandidate.model_validate(raw)


def test_invalid_clock_format_is_rejected() -> None:
    raw = copy.deepcopy(load("itinerary_plan"))
    raw["days"][0]["nodes"][0]["start_time"] = "9:30"
    with pytest.raises(ValidationError):
        ItineraryPlan.model_validate(raw)


def test_reversed_date_range_is_rejected() -> None:
    raw = copy.deepcopy(load("trip_profile"))
    raw["end_date"] = "2026-09-01"
    with pytest.raises(ValidationError, match="end_date"):
        TripProfile.model_validate(raw)


def test_time_window_order_is_enforced() -> None:
    raw = copy.deepcopy(load("resource_candidates")[0])
    raw["availability"]["time_windows"] = [{"start": "16:00", "end": "09:00"}]
    with pytest.raises(ValidationError, match="TimeWindow"):
        ResourceCandidate.model_validate(raw)


def test_validated_guide_requires_last_updated() -> None:
    raw = copy.deepcopy(load("travel_guide"))
    raw["sources_and_freshness"]["last_updated"] = None
    with pytest.raises(ValidationError, match="last_updated"):
        TravelGuide.model_validate(raw)


def test_modify_guide_requires_change_payload() -> None:
    raw = copy.deepcopy(load("user_action"))
    raw["payload"] = None
    with pytest.raises(ValidationError, match="payload"):
        UserAction.model_validate(raw)


def test_invalid_change_type_is_rejected() -> None:
    raw = copy.deepcopy(load("user_action"))
    raw["payload"]["change_type"] = "MAKE_IT_NICER"
    with pytest.raises(ValidationError):
        UserAction.model_validate(raw)
