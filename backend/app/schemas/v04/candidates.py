"""资源候选的判别联合类型（`CONTRACTS.md` §5）。

A 线不得返回无类型的任意 dict；所有资源候选必须能按 `resource_type`
落到下面某一个具体模型上。
"""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import BaseModel, Field, TypeAdapter

from .models import (
    IntercityOption,
    LodgingAreaCandidate,
    LodgingCandidate,
    ResourceCandidateBase,
    RestaurantCandidate,
    VisitPlaceCandidate,
)

#: 以 `resource_type` 为判别字段的资源候选联合类型（Q4 拍板，2026-09-24）。
#: `IntercityOption`（option_id）与 `PreparationRule`（rule_id）不属于本联合类型。
ResourceCandidateUnion = Annotated[
    Union[
        VisitPlaceCandidate,
        LodgingCandidate,
        RestaurantCandidate,
        LodgingAreaCandidate,
    ],
    Field(discriminator="resource_type"),
]

RESOURCE_CANDIDATE_ADAPTER = TypeAdapter(ResourceCandidateUnion)


def parse_resource_candidate(payload: dict) -> ResourceCandidateUnion:
    """按 `resource_type` 解析一个资源候选。"""

    return RESOURCE_CANDIDATE_ADAPTER.validate_python(payload)
