"""C3 前置过滤：不可用地点不得进入规划。

契约依据：

* `CONTRACTS.md` §14 不变量 2「`UNAVAILABLE` 资源不得进入计划」；
* §14 不变量 3「`UNKNOWN` 关键事实阻止 VERIFIED 模式发布」；
* §1.3 `AvailabilityStatus = AVAILABLE | CONDITIONAL | UNAVAILABLE | UNKNOWN`；
* `docs/SCOPE_MATRIX.md` 景点行的验收方式「不可用地点被前置过滤」。

本模块是**纯函数**，输入输出都是 v0.4 契约对象，可单独测试，
不依赖数据库、MCP 或 LangGraph。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.schemas import ResourceCandidateBase, RunMode
from app.schemas.v04.mcp import GetResourceAvailabilityResponse

AvailabilityLookup = Callable[[str, date], GetResourceAvailabilityResponse]


@dataclass(frozen=True)
class ExcludedCandidate:
    """被排除的候选及原因。必须能回指到具体资源，不允许静默丢弃。"""

    resource_id: str
    status: str
    reason: str


@dataclass
class FilterResult:
    """前置过滤结果。"""

    #: 可直接进入规划
    usable: list[ResourceCandidateBase] = field(default_factory=list)
    #: 有条件可用：可以进入规划，但必须带上条件说明（预约、天气确认等）
    conditional: list[ResourceCandidateBase] = field(default_factory=list)
    #: 资料不足：不得作为无条件主方案
    unknown: list[ResourceCandidateBase] = field(default_factory=list)
    #: 明确不可用：绝不进入规划
    excluded: list[ExcludedCandidate] = field(default_factory=list)

    @property
    def plannable(self) -> list[ResourceCandidateBase]:
        """可以交给规划器的集合：可用 + 有条件可用。"""

        return [*self.usable, *self.conditional]

    @property
    def has_unconditional_primary(self) -> bool:
        """是否存在无条件主方案（`UNKNOWN` 资源不得充当主方案）。"""

        return bool(self.usable)


def filter_candidates(
    candidates: Sequence[ResourceCandidateBase],
    *,
    travel_date: date | None = None,
    availability_lookup: AvailabilityLookup | None = None,
    run_mode: RunMode = RunMode.DEMO,
) -> FilterResult:
    """按可用性把候选分成 可用 / 有条件 / 未知 / 排除 四类。

    判定顺序（后一步只在需要时执行）：

    1. 先看候选对象自带的 `availability_status`；
    2. 若给了 `travel_date` 且 `availability_lookup` 可用，则以**当日可用性**为准
       （这样"某天临时闭馆"能被正确过滤）；
    3. `VERIFIED` 模式下 `UNKNOWN` 一律不得进入规划。
    """

    result = FilterResult()
    for candidate in candidates:
        status = _status_of(candidate)
        reason = _reason_of(candidate)

        if travel_date is not None and availability_lookup is not None:
            daily = availability_lookup(candidate.resource_id, travel_date)
            status = daily.status
            if daily.reason:
                reason = daily.reason

        if status == "AVAILABLE":
            result.usable.append(candidate)
        elif status == "CONDITIONAL":
            result.conditional.append(candidate)
        elif status == "UNAVAILABLE":
            result.excluded.append(
                ExcludedCandidate(
                    resource_id=candidate.resource_id,
                    status=status,
                    reason=reason or "资源在该日期不可用",
                )
            )
        else:  # UNKNOWN
            if run_mode is RunMode.VERIFIED:
                result.excluded.append(
                    ExcludedCandidate(
                        resource_id=candidate.resource_id,
                        status=status,
                        reason="关键事实未知，VERIFIED 模式不得使用",
                    )
                )
            else:
                result.unknown.append(candidate)
    return result


def is_usable(
    candidate: ResourceCandidateBase, result: FilterResult
) -> bool:
    """该候选是否已被判定为可进入规划（方便节点里做断言）。"""

    ids = {item.resource_id for item in result.plannable}
    return candidate.resource_id in ids


def _status_of(candidate: ResourceCandidateBase) -> str:
    status = getattr(candidate, "availability_status", None)
    if status is None:
        # 模型允许不带该字段时视为未知，绝不默认可用
        return "UNKNOWN"
    return str(getattr(status, "value", status))


def _reason_of(candidate: ResourceCandidateBase) -> str | None:
    for name in ("availability_reason", "reason", "unavailability_reason"):
        value = getattr(candidate, name, None)
        if isinstance(value, str) and value:
            return value
    return None
