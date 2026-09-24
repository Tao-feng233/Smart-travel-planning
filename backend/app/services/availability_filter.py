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


# --- 整段行程的前置过滤（接入 LangGraph 时使用） -----------------------------


@dataclass
class TripFilterResult:
    """按整段行程的每一天检查可用性之后的过滤结果。

    与 `FilterResult` 的差别：`FilterResult` 只按**一个**日期（或候选自带状态）分类，
    而行程是多天的，"整体可用但行程中某几天闭馆" 必须能被表达出来，
    否则规划器会把资源排到闭馆当天。因此这里逐日查询并记录：

    * 每天都不可以用 → 排除（`CONTRACTS.md` §14 不变量 2）；
    * 部分日期不可用   → 保留为**有条件**候选，并把禁排日期记进
      `unavailable_dates`，供 C4 规划时做增量检查。
    """

    usable: list[ResourceCandidateBase] = field(default_factory=list)
    conditional: list[ResourceCandidateBase] = field(default_factory=list)
    unknown: list[ResourceCandidateBase] = field(default_factory=list)
    excluded: list[ExcludedCandidate] = field(default_factory=list)
    #: 资源 ID → 行程期内明确不可用的日期（该资源不得排在这几天）
    unavailable_dates: dict[str, list[date]] = field(default_factory=dict)
    #: 本次实际检查过的日期
    checked_dates: list[date] = field(default_factory=list)

    @property
    def plannable(self) -> list[ResourceCandidateBase]:
        """可直接交给规划器的集合：可用 + 有条件可用（`UNKNOWN` 不算）。"""

        return [*self.usable, *self.conditional]

    @property
    def all_candidates(self) -> list[ResourceCandidateBase]:
        """未被排除的全部候选（含 `UNKNOWN`，只可作降级备用，不得当主方案）。"""

        return [*self.usable, *self.conditional, *self.unknown]

    @property
    def has_unconditional_primary(self) -> bool:
        """是否存在无条件主方案（`UNKNOWN` 资源不得充当主方案）。"""

        return bool(self.usable)

    @property
    def has_any_candidate(self) -> bool:
        """是否还有任何可用/可降级使用的候选；为 False 时只能报资料不足。"""

        return bool(self.all_candidates)


def filter_candidates_for_trip(
    candidates: Sequence[ResourceCandidateBase],
    *,
    travel_dates: Sequence[date],
    availability_lookup: AvailabilityLookup,
    run_mode: RunMode = RunMode.DEMO,
) -> TripFilterResult:
    """逐日检查可用性，把候选分成 可用 / 有条件 / 未知 / 排除 四类。

    判定规则（按顺序）：

    1. 对行程中的每一天调用 `availability_lookup`，**当日状态以 Provider 为准**；
    2. 每一天都 `UNAVAILABLE` → 排除，并保留原因（不静默丢弃）；
    3. 部分日期 `UNAVAILABLE` → 归入有条件候选，禁排日期记入 `unavailable_dates`；
    4. 其余情况取当天状态里最保守的一档：有 `UNKNOWN` 即 `UNKNOWN`，
       否则有 `CONDITIONAL` 即 `CONDITIONAL`，全为 `AVAILABLE` 才 `AVAILABLE`；
    5. `VERIFIED` 模式下 `UNKNOWN` 一律排除（§14 不变量 3）。
    """

    dates = list(travel_dates)
    result = TripFilterResult(checked_dates=dates)

    for candidate in candidates:
        base_reason = _reason_of(candidate)
        statuses: list[str] = []
        blocked: list[date] = []
        blocked_reason: str | None = None

        for travel_date in dates:
            daily = availability_lookup(candidate.resource_id, travel_date)
            status = str(getattr(daily.status, "value", daily.status))
            statuses.append(status)
            if status == "UNAVAILABLE":
                blocked.append(travel_date)
                blocked_reason = daily.reason or blocked_reason

        if not statuses:
            # 没有可检查的日期：退回候选自带状态，语义与 filter_candidates 一致
            statuses = [_status_of(candidate)]

        if all(status == "UNAVAILABLE" for status in statuses):
            result.excluded.append(
                ExcludedCandidate(
                    resource_id=candidate.resource_id,
                    status="UNAVAILABLE",
                    reason=blocked_reason
                    or base_reason
                    or "资源在行程期内不可用",
                )
            )
            continue

        effective = _worst_status(statuses)

        if blocked:
            # 有明确不能排的日期，就不是无条件主方案
            result.unavailable_dates[candidate.resource_id] = blocked
            result.conditional.append(candidate)
            continue

        if effective == "AVAILABLE":
            result.usable.append(candidate)
        elif effective == "CONDITIONAL":
            result.conditional.append(candidate)
        elif run_mode is RunMode.VERIFIED:
            result.excluded.append(
                ExcludedCandidate(
                    resource_id=candidate.resource_id,
                    status=effective,
                    reason="关键事实未知，VERIFIED 模式不得使用",
                )
            )
        else:
            result.unknown.append(candidate)

    return result


def _worst_status(statuses: Sequence[str]) -> str:
    """取当天状态里最保守的一档：UNKNOWN > CONDITIONAL > AVAILABLE。"""

    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    if "CONDITIONAL" in statuses:
        return "CONDITIONAL"
    return "AVAILABLE"
