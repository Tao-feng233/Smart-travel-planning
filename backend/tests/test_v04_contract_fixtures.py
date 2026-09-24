"""把仓库根目录 `fixtures/` 的契约测试接进 pytest。

这是 `docs/SHARED_SCHEMA_HANDOFF.md` 第 3 节的完成标准：
`fixtures/valid` 全部通过、`fixtures/invalid` 全部按预期失败、
业务用例（锁定节点不可变、Draft 转换）全部符合预期。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import v04

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(kind: str) -> list[Path]:
    return sorted((FIXTURES / kind).glob("*.json"))


@pytest.mark.parametrize("path", _cases("valid"), ids=lambda p: p.name)
def test_valid_fixtures_pass(path: Path) -> None:
    payload = _load(path)
    model = v04.MODEL_REGISTRY[payload["model"]]
    model.model_validate(payload["data"])


@pytest.mark.parametrize("path", _cases("invalid"), ids=lambda p: p.name)
def test_invalid_fixtures_fail(path: Path) -> None:
    payload = _load(path)
    model = v04.MODEL_REGISTRY[payload["model"]]
    with pytest.raises(ValidationError):
        model.model_validate(payload["data"])


@pytest.mark.parametrize("path", _cases("business"), ids=lambda p: p.name)
def test_business_fixtures(path: Path) -> None:
    payload = _load(path)
    case = payload["case"]

    if case == "locked_node_immutability":
        violation = any(
            payload["before_nodes"].get(node_id) != payload["after_nodes"].get(node_id)
            for node_id in payload["locked_node_ids"]
        )
        assert violation == payload["expect_violation"]
        return

    if case == "draft_finalize_success":
        draft = v04.TripProfileDraft.model_validate(payload["draft"])
        assert draft.compute_missing_fields() == payload["expect_missing_before"]
        profile = v04.finalize_trip_profile(draft)
        for field, expected in payload["expect"].items():
            actual = getattr(profile, field)
            if hasattr(actual, "model_dump"):
                actual = actual.model_dump()
            assert actual == expected, f"{field} 不符合预期"
        return

    if case == "draft_finalize_failure":
        draft = v04.TripProfileDraft.model_validate(payload["draft"])
        assert draft.compute_missing_fields() == payload["expect_missing_fields"]
        with pytest.raises(v04.IncompleteProfileError) as excinfo:
            v04.finalize_trip_profile(draft)
        assert excinfo.value.missing_fields == payload["expect_missing_fields"]
        return

    pytest.fail(f"未知业务用例：{case}")


def test_mcp_tool_contract_is_complete() -> None:
    """§12 的 9 个工具都要有 Request/Response 模型。"""

    assert len(v04.MCP_TOOL_MODELS) == 9
    for name, (request, response) in v04.MCP_TOOL_MODELS.items():
        assert request.__name__ and response.__name__, name


def test_resource_union_members_expose_base_fields() -> None:
    """Q4 拍板：联合类型成员统一继承 ResourceCandidateBase，字段名一致。"""

    base_fields = set(v04.ResourceCandidateBase.model_fields)
    for model in (
        v04.VisitPlaceCandidate,
        v04.LodgingCandidate,
        v04.RestaurantCandidate,
        v04.LodgingAreaCandidate,
    ):
        assert issubclass(model, v04.ResourceCandidateBase)
        missing = base_fields - set(model.model_fields)
        assert not missing, f"{model.__name__} 缺少公共字段：{sorted(missing)}"


def test_lodging_candidate_uses_shared_primary_key() -> None:
    """住宿候选不再使用 `lodging_id` 作为共享主键。"""

    assert "resource_id" in v04.LodgingCandidate.model_fields
    assert "lodging_id" not in v04.LodgingCandidate.model_fields


def test_non_union_types_keep_their_own_ids() -> None:
    """IntercityOption 与 PreparationRule 不属于联合类型，保留各自主键。"""

    assert "option_id" in v04.IntercityOption.model_fields
    assert "rule_id" in v04.PreparationRule.model_fields
    assert "resource_type" not in v04.IntercityOption.model_fields


def test_union_discriminator_resolves_members() -> None:
    kind = v04.ResourceCandidateUnion.__metadata__[0].discriminator
    assert kind == "resource_type"


def test_all_handoff_objects_are_implemented() -> None:
    """SHARED_SCHEMA_HANDOFF 第 2 节列出的对象必须都已实现并可导入。"""

    from pydantic import BaseModel

    required = {
        "Money", "TripProfile", "DestinationRequest", "Constraint",
        "DestinationCoverageSnapshot", "PlanningReadinessEvaluation",
        "DestinationRecommendation", "FactRecord", "Evidence", "PlanningFact",
        "DataSnapshot", "ResourceCandidateBase", "VisitPlaceCandidate",
        "LodgingCandidate", "RestaurantCandidate", "IntercityOption",
        "PreparationRule", "TripSegment", "StaySegment", "PlanNode", "TravelLeg",
        "DayPlan", "CostItem", "BudgetSummary", "ItineraryPlan", "RepairOption",
        "Conflict", "AlternativePlan", "GuideNode", "GuideDay",
        "TripSummarySection", "ArrivalAndDepartureSection", "PreparationSection",
        "LodgingSection", "BudgetAndAlternativesSection",
        "SourcesAndFreshnessSection", "TravelGuide", "PlanState", "UserAction",
        "VersionLineage", "TripProfileDraft",
    }
    missing = sorted(
        name
        for name in required
        if not (hasattr(v04, name) and issubclass(getattr(v04, name), BaseModel))
    )
    assert not missing, f"未实现的对象：{missing}"
