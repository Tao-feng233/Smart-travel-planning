"""`TripProfileDraft`：对话过程中的不完整旅行画像。

契约依据：`CONTRACTS.md` §2.4 / §2.5（2026-09-24 三人确认）。

设计要点：

* 正式 `TripProfile` **保持关键字段必填**，不做成"全字段可空"；
* 尚未问全的画像由 `TripProfileDraft` 承载，除 `session_id` 外均可为空；
* `missing_fields` 只属于 Draft；
* Draft 补齐后由 `finalize_trip_profile` 转换为正式 `TripProfile`，
  缺关键字段时抛 `IncompleteProfileError`，不得生成正式对象。

> 注意：本模块目前沿用 v0.3 的字段集合（`Budget` 等）。C1 全量重建 v0.4
> Schema 时，字段名会随 `CONTRACTS.md` v0.4 一起升级（`Money`、`Constraint` 等）。
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .contracts import (
    Budget,
    ContractModel,
    DestinationMode,
    DestinationRequest,
    TravelerComposition,
    TripProfile,
)

#: `finalize_trip_profile` 必须由用户提供、系统不得替他假设的字段。
FINALIZE_REQUIRED_FIELDS: tuple[str, ...] = (
    "departure_city",
    "start_date",
    "end_date",
    "traveler_count",
    "budget",
)


class IncompleteProfileError(ValueError):
    """Draft 信息不全时被强行转换为正式 `TripProfile`。"""

    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        super().__init__(
            "TripProfileDraft 尚未补全，缺少字段：" + ", ".join(missing_fields)
        )


class TripProfileDraft(ContractModel):
    """不完整画像：除 `session_id` 外所有字段允许为空。"""

    session_id: str
    departure_city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    traveler_count: int | None = None
    traveler_composition: TravelerComposition | None = None
    mobility_constraints: list[str] = Field(default_factory=list)
    budget: Budget | None = None
    pace: str | None = None
    interests: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    fixed_facts: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    destination_mode: DestinationMode = DestinationMode.UNKNOWN
    destination_requests: list[DestinationRequest] = Field(default_factory=list)
    #: 仍需用户补充的关键字段，由系统计算
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_partial_dates(self) -> "TripProfileDraft":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date 不得早于 start_date")
        return self

    def compute_missing_fields(self) -> list[str]:
        """按固定顺序返回仍需补充的关键字段。"""

        return [
            name for name in FINALIZE_REQUIRED_FIELDS
            if getattr(self, name, None) is None
        ]


def finalize_trip_profile(draft: TripProfileDraft) -> TripProfile:
    """Draft → 正式 `TripProfile`（`CONTRACTS.md` §2.5）。

    补全规则：

    * `traveler_composition` 未给出时按成人计（adults = traveler_count）；
    * 其余字段直接沿用；`Budget.flexibility` 已由契约给出默认值。
    """

    missing = draft.compute_missing_fields()
    if missing:
        raise IncompleteProfileError(missing)

    assert draft.traveler_count is not None
    composition = draft.traveler_composition or TravelerComposition(
        adults=draft.traveler_count
    )
    if composition.adults + composition.children + composition.seniors != draft.traveler_count:
        raise IncompleteProfileError(["traveler_composition"])

    return TripProfile(
        session_id=draft.session_id,
        departure_city=draft.departure_city,
        start_date=draft.start_date,
        end_date=draft.end_date,
        traveler_count=draft.traveler_count,
        traveler_composition=composition,
        mobility_constraints=draft.mobility_constraints,
        budget=draft.budget,
        pace=draft.pace,
        interests=draft.interests,
        avoidances=draft.avoidances,
        fixed_facts=draft.fixed_facts,
        hard_constraints=draft.hard_constraints,
        soft_preferences=draft.soft_preferences,
        destination_mode=draft.destination_mode,
        destination_requests=draft.destination_requests,
    )
