"""资源候选的判别联合类型（`CONTRACTS.md` §5）。

A 线不得返回无类型的任意 dict；所有资源候选必须能按 `resource_type`
落到下面某一个具体模型上。
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from .models import (
    IntercityOption,
    LodgingCandidate,
    RestaurantCandidate,
    VisitPlaceCandidate,
)


class ResourceCandidateBase(BaseModel):
    """§5.1 定义的公共字段契约。

    具体模型（`VisitPlaceCandidate` 等）通过继承之外的方式满足这些字段；
    `backend/tests/test_v04_schema.py` 会校验它们确实都具备这些字段。
    """

    resource_id: str
    resource_type: str
    destination_id: str
    area_id: str | None = None
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    categories: list[str] = Field(default_factory=list)
    suggested_duration_minutes: int | None = None
    availability_status: Literal[
        "AVAILABLE", "CONDITIONAL", "UNAVAILABLE", "UNKNOWN"
    ] = "UNKNOWN"
    planning_fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


#: 以 `resource_type` 为判别字段的资源候选联合类型。
#: 注：`LODGING_AREA` 已在 §1.3 的枚举中，但基线与附录 A 尚未给出独立模型，
#: 待三人确认后补入（已登记在 docs/contract-open-questions.md）。
ResourceCandidateUnion = Annotated[
    Union[
        VisitPlaceCandidate,
        LodgingCandidate,
        RestaurantCandidate,
        IntercityOption,
    ],
    Field(discriminator="resource_type"),
]

RESOURCE_CANDIDATE_ADAPTER = TypeAdapter(ResourceCandidateUnion)


def parse_resource_candidate(payload: dict) -> ResourceCandidateUnion:
    """按 `resource_type` 解析一个资源候选。"""

    return RESOURCE_CANDIDATE_ADAPTER.validate_python(payload)
