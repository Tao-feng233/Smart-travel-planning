"""C5 计划验证器：检查 `ItineraryPlan` 的可行性，产出 `Conflict[]` 与修复选项。

契约依据：

* `CONTRACTS.md` §8.1 `RepairOption` / §8.2 `Conflict`（类型与严重度取值）；
* §14 不变量：`UNAVAILABLE` 不得进计划、`UNKNOWN` 关键事实阻止 VERIFIED 发布、
  `INVALID` 不得生成 READY 攻略、固定事实与未授权的硬约束不得被自动突破；
* `SCOPE_MATRIX.md` 的验收方式「验证失败不能把计划标成 VALID」。

设计边界（重要）：

```text
本模块只做"检查 + 给出修复选项"，不修改计划内容、不产生新版本。
套用修复、产出 v2 是 C6 的事（闭馆替换与突发重走同一套机制）。
因此这里唯一会写回计划的是 plan_validation_status 与 conflict_ids。
```

严重度口径：

```text
ERROR   → 计划不可用：UNAVAILABLE 资源、节点重叠、超出用户日/预算硬限、
          VERIFIED 模式下的未知关键事实 → plan_validation_status = INVALID
WARNING → 可用但要提醒：预约要求、数据缺口、节奏偏紧、接近预算上限
```
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Sequence

from app.schemas import (
    Conflict,
    ItineraryPlan,
    PlanNode,
    PlanValidationStatus,
    RepairOption,
    ResourceCandidateBase,
    RestaurantCandidate,
    RunMode,
    TripProfile,
    VisitPlaceCandidate,
)
from app.services.availability_filter import TripFilterResult

#: 一天里"游玩 + 用餐"的总时长超过这个数就算强度偏高（分钟）
_HEAVY_DAY_MINUTES = 8 * 60
#: 一天里的移动时间超过这个数就提示里程过长（分钟）
_LONG_TRAVEL_MINUTES = 120
#: 预算用到这个比例以上给提醒
_BUDGET_WARN_RATIO = 0.9


@dataclass
class ValidationResult:
    """验证结果：状态 + 冲突清单 + 说明。"""

    status: PlanValidationStatus
    conflicts: list[Conflict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Conflict]:
        return [item for item in self.conflicts if item.severity == "ERROR"]


def validate_plan(
    plan: ItineraryPlan,
    *,
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase] = (),
    filter_result: TripFilterResult | None = None,
    prior_conflicts: Sequence[Conflict] = (),
    run_mode: RunMode = RunMode.DEMO,
) -> ValidationResult:
    """按契约 §8/§14 检查计划，返回状态与冲突清单。"""

    nodes = {node.node_id: node for node in plan.nodes}
    resource_by_id = {item.resource_id: item for item in candidates}
    # 用 getattr 兜住"误传了单日版 FilterResult"的情况：宁可少判，也不能崩
    excluded = {
        item.resource_id for item in getattr(filter_result, "excluded", ()) or ()
    }
    blocked = dict(getattr(filter_result, "unavailable_dates", {}) or {})

    # `prior_conflicts` 只通过 `_check_data_gaps` 进来一次（它会按运行模式调整严重度），
    # 这里不能先塞一遍，否则同一条数据缺口会在回复里出现两次。
    conflicts: list[Conflict] = []
    conflicts.extend(
        _check_resource_states(plan, nodes, resource_by_id, excluded, blocked, candidates)
    )
    conflicts.extend(_check_opening_hours(plan, nodes, resource_by_id))
    conflicts.extend(_check_overlaps(plan, nodes))
    conflicts.extend(_check_day_window(plan, nodes, profile))
    conflicts.extend(_check_budget(plan, profile))
    conflicts.extend(_check_intensity(plan, nodes, profile))
    conflicts.extend(_check_data_gaps(prior_conflicts, run_mode))

    notes: list[str] = []
    errors = [item for item in conflicts if item.severity == "ERROR"]
    if errors:
        # §14 不变量 4：有 ERROR 就不允许标成 VALID
        status = PlanValidationStatus.INVALID
        notes.append(f"发现 {len(errors)} 项必须处理的问题，计划不能直接使用。")
    else:
        status = PlanValidationStatus.VALID
        warnings = [item for item in conflicts if item.severity == "WARNING"]
        if warnings:
            notes.append(f"计划可用，但有 {len(warnings)} 项提醒。")
    return ValidationResult(status=status, conflicts=conflicts, notes=notes)


def attach_validation(plan: ItineraryPlan, result: ValidationResult) -> ItineraryPlan:
    """把验证结论写回计划（只改状态与冲突引用，重新走一次契约校验）。"""

    payload = plan.model_dump()
    payload["plan_validation_status"] = result.status
    payload["conflict_ids"] = [item.conflict_id for item in result.conflicts]
    # 走一次 model_validate：若"VALID 却超预算"这类不变量被破坏，会当场报错
    return ItineraryPlan.model_validate(payload)


# --- 各项检查 ---------------------------------------------------------------


def _check_resource_states(
    plan: ItineraryPlan,
    nodes: dict[str, PlanNode],
    resource_by_id: dict[str, ResourceCandidateBase],
    excluded: set[str],
    blocked: dict[str, list[date]],
    candidates: Sequence[ResourceCandidateBase],
) -> list[Conflict]:
    """§14 不变量 2：`UNAVAILABLE` 资源不得进入计划（含"当天闭馆"）。"""

    conflicts: list[Conflict] = []
    for node in plan.nodes:
        resource_id = node.resource_id
        if resource_id is None:
            continue
        day = node.start_at.date()
        reason: str | None = None
        if resource_id in excluded:
            reason = "该资源已被前置过滤排除（行程期内不可用）"
        elif day in blocked.get(resource_id, ()):
            reason = f"该资源在 {day.isoformat()} 不可用"
        else:
            resource = resource_by_id.get(resource_id)
            if resource is not None and resource.availability_status == "UNAVAILABLE":
                reason = "该资源当前标记为 UNAVAILABLE"
        if reason is None:
            continue
        alternatives = _replacement_options(
            plan, node, day, candidates, excluded, blocked
        )
        conflicts.append(
            Conflict(
                conflict_id=f"conflict_unavailable_{node.node_id}",
                type="OPENING_HOURS",
                severity="ERROR",
                scope="NODE",
                message=f"{node.node_id} 使用了不可用资源 {resource_id}：{reason}。",
                affected_node_ids=[node.node_id],
                repair_options=alternatives,
                status="OPEN",
            )
        )
    return conflicts


def _replacement_options(
    plan: ItineraryPlan,
    node: PlanNode,
    day: date,
    candidates: Sequence[ResourceCandidateBase],
    excluded: set[str],
    blocked: dict[str, list[date]],
) -> list[RepairOption]:
    """为闭馆/不可用节点找同日可用的替代资源（P0 验收用的"闭馆替换"）。"""

    used = {item.resource_id for item in plan.nodes}
    usable = [
        item.resource_id
        for item in candidates
        if item.resource_id not in used
        and item.resource_id not in excluded
        and day not in blocked.get(item.resource_id, ())
    ]
    if not usable:
        return [
            RepairOption(
                repair_option_id=f"repair_remove_{node.node_id}",
                action="REMOVE_NODE",
                description="当天没有可用替代资源，只能去掉这个节点或换日期。",
                affected_node_ids=[node.node_id],
                requires_user_confirmation=True,
            )
        ]
    return [
        RepairOption(
            repair_option_id=f"repair_replace_{node.node_id}",
            action="REPLACE_RESOURCE",
            description=(
                f"用 {usable[0]} 替换 {node.resource_id}"
                f"（同日可用候选：{', '.join(usable[:3])}）。"
            ),
            affected_node_ids=[node.node_id],
        ),
        RepairOption(
            repair_option_id=f"repair_move_{node.node_id}",
            action="MOVE_NODE",
            description="或把该节点挪到该资源可用的日期。",
            affected_node_ids=[node.node_id],
            requires_user_confirmation=True,
        ),
    ]


def _check_opening_hours(
    plan: ItineraryPlan,
    nodes: dict[str, PlanNode],
    resource_by_id: dict[str, ResourceCandidateBase],
) -> list[Conflict]:
    """节点必须落在资源的开放窗口内（`TimeWindow` 来自 Provider）。"""

    conflicts: list[Conflict] = []
    for node in plan.nodes:
        if node.node_type not in ("ATTRACTION", "MEAL"):
            continue
        resource = resource_by_id.get(node.resource_id or "")
        windows = getattr(resource, "opening_windows", None) if resource else None
        if not windows or _inside_any_window(node, windows):
            continue
        conflicts.append(
            Conflict(
                conflict_id=f"conflict_opening_{node.node_id}",
                type="OPENING_HOURS",
                severity="ERROR",
                scope="NODE",
                message=(
                    f"{node.node_id}（{node.resource_id}）的 "
                    f"{node.start_at.time()}–{node.end_at.time()} 不在开放时间内。"
                ),
                affected_node_ids=[node.node_id],
                repair_options=[
                    RepairOption(
                        repair_option_id=f"repair_move_{node.node_id}",
                        action="MOVE_NODE",
                        description="把节点挪进开放时间，或换一个同时段的资源。",
                        affected_node_ids=[node.node_id],
                    )
                ],
                status="OPEN",
            )
        )
    return conflicts


def _inside_any_window(node: PlanNode, windows: Iterable) -> bool:
    # 比较本地墙上时间（`time()` 而不是 `timetz()`）：窗口来自不同资源时
    # tzinfo 可能不同，直接比较 aware time 会抛 TypeError。
    # 跨午夜的节点一律不算"在开放时间内"：`time()` 比较会被 00:00 骗过去。
    if node.end_at.date() != node.start_at.date():
        return False
    for window in windows:
        opens = window.start_at.time()
        closes = window.end_at.time()
        if node.start_at.time() >= opens and node.end_at.time() <= closes:
            return True
    return False


def _check_overlaps(
    plan: ItineraryPlan, nodes: dict[str, PlanNode]
) -> list[Conflict]:
    """同一天节点不得重叠（§7.8 不变量）。"""

    conflicts: list[Conflict] = []
    by_day: dict[date, list[PlanNode]] = defaultdict(list)
    for node in plan.nodes:
        by_day[node.start_at.date()].append(node)
    for day, items in by_day.items():
        ordered = sorted(items, key=lambda item: item.start_at)
        for previous, following in zip(ordered, ordered[1:]):
            if following.start_at < previous.end_at:
                conflicts.append(
                    Conflict(
                        conflict_id=f"conflict_overlap_{previous.node_id}_{following.node_id}",
                        type="TIME_WINDOW",
                        severity="ERROR",
                        scope="DAY",
                        message=(
                            f"{day.isoformat()} 的 {previous.node_id} 与 "
                            f"{following.node_id} 时间重叠。"
                        ),
                        affected_node_ids=[previous.node_id, following.node_id],
                        repair_options=[
                            RepairOption(
                                repair_option_id=f"repair_reorder_{day.isoformat()}",
                                action="REORDER_NODES",
                                description="重排当天节点顺序，或把其中一个挪到别的时段。",
                                affected_node_ids=[
                                    previous.node_id,
                                    following.node_id,
                                ],
                            )
                        ],
                        status="OPEN",
                    )
                )
    return conflicts


def _check_day_window(
    plan: ItineraryPlan, nodes: dict[str, PlanNode], profile: TripProfile
) -> list[Conflict]:
    """尊重用户说的"不想早起 / 别太晚"（`earliest_day_start` / `latest_day_end`）。"""

    conflicts: list[Conflict] = []
    earliest = _parse_moment(profile.earliest_day_start)
    latest = _parse_moment(profile.latest_day_end)
    if earliest is None and latest is None:
        return conflicts
    for node in plan.nodes:
        if earliest is not None and node.start_at.time() < earliest:
            conflicts.append(
                _window_conflict(
                    node,
                    f"{node.node_id} 在 {node.start_at.time()} 开始，早于用户要求的 "
                    f"不早于 {earliest}。",
                    "MOVE_NODE",
                )
            )
        if latest is not None and node.end_at.time() > latest:
            conflicts.append(
                _window_conflict(
                    node,
                    f"{node.node_id} 到 {node.end_at.time()} 才结束，晚于用户要求的 "
                    f"不晚于 {latest}。",
                    "MOVE_NODE",
                )
            )
    return conflicts


def _window_conflict(node: PlanNode, message: str, action: str) -> Conflict:
    return Conflict(
        conflict_id=f"conflict_daywindow_{node.node_id}",
        type="TIME_WINDOW",
        severity="ERROR",
        scope="NODE",
        message=message,
        affected_node_ids=[node.node_id],
        repair_options=[
            RepairOption(
                repair_option_id=f"repair_{action.lower()}_{node.node_id}",
                action=action,
                description="调整该节点的时段以满足用户时间要求。",
                affected_node_ids=[node.node_id],
            )
        ],
        status="OPEN",
    )


def _check_budget(plan: ItineraryPlan, profile: TripProfile) -> list[Conflict]:
    """预算只能由 `CostItem[]` 算（§7.7）；超限是 ERROR，接近上限是 WARNING。"""

    summary = plan.budget_summary
    limit = summary.total_limit
    if limit <= 0:
        return []
    if summary.estimated_min_total > limit:
        options = [
            RepairOption(
                repair_option_id="repair_replace_cheaper",
                action="REPLACE_RESOURCE",
                description="换成更便宜的住宿或餐厅候选。",
            ),
            RepairOption(
                repair_option_id="repair_remove_node",
                action="REMOVE_NODE",
                description="去掉一个花费最高的自费项目。",
                requires_user_confirmation=True,
            ),
        ]
        if profile.budget_flexibility == "NEGOTIABLE":
            options.append(
                RepairOption(
                    repair_option_id="repair_relax_budget",
                    action="RELAX_NEGOTIABLE_CONSTRAINT",
                    description="用户此前表示预算可协商，可以调整预算上限。",
                    requires_user_confirmation=True,
                )
            )
        else:
            # 预算被标成不可协商：只能问用户，不得自动突破
            options.append(
                RepairOption(
                    repair_option_id="repair_ask_budget",
                    action="REQUEST_USER_CHOICE",
                    description="预算被设为不可协商，需要用户决定放宽或删减项目。",
                    requires_user_confirmation=True,
                )
            )
        return [
            Conflict(
                conflict_id="conflict_budget_exceeded",
                type="BUDGET_EXCEEDED",
                severity="ERROR",
                scope="WHOLE_GUIDE",
                message=(
                    f"预计最低花费 ¥{summary.estimated_min_total:.0f} 已经超过预算上限 "
                    f"¥{limit:.0f}。"
                ),
                repair_options=options,
                status="OPEN",
            )
        ]
    if summary.estimated_max_total > limit * _BUDGET_WARN_RATIO:
        return [
            Conflict(
                conflict_id="conflict_budget_tight",
                type="BUDGET_EXCEEDED",
                severity="WARNING",
                scope="WHOLE_GUIDE",
                message=(
                    f"预计花费最高 ¥{summary.estimated_max_total:.0f}，"
                    f"已经接近预算上限 ¥{limit:.0f}。"
                ),
                status="OPEN",
            )
        ]
    return []


def _check_intensity(
    plan: ItineraryPlan, nodes: dict[str, PlanNode], profile: TripProfile
) -> list[Conflict]:
    """节奏与行动不便约束：太满或移动太多都提醒。"""

    conflicts: list[Conflict] = []
    by_day: dict[date, list[PlanNode]] = defaultdict(list)
    for node in plan.nodes:
        by_day[node.start_at.date()].append(node)
    legs_by_day: dict[date, int] = defaultdict(int)
    for leg in plan.travel_legs:
        legs_by_day[leg.depart_at.date()] += leg.duration_minutes

    for day, items in by_day.items():
        busy = sum(
            int((item.end_at - item.start_at).total_seconds() // 60)
            for item in items
            if item.node_type in ("ATTRACTION", "MEAL")
        )
        if busy > _HEAVY_DAY_MINUTES:
            conflicts.append(
                Conflict(
                    conflict_id=f"conflict_intensity_{day.isoformat()}",
                    type="DAILY_INTENSITY",
                    severity="WARNING",
                    scope="DAY",
                    message=f"{day.isoformat()} 安排了 {busy // 60} 小时活动，节奏偏紧。",
                    affected_node_ids=[item.node_id for item in items],
                    repair_options=[
                        RepairOption(
                            repair_option_id=f"repair_rest_{day.isoformat()}",
                            action="ADD_REST",
                            description="在当天插入休息或删掉一个景点。",
                            affected_node_ids=[item.node_id for item in items],
                        )
                    ],
                    status="OPEN",
                )
            )
        travel = legs_by_day.get(day, 0)
        if profile.mobility_constraints and travel > _LONG_TRAVEL_MINUTES:
            conflicts.append(
                Conflict(
                    conflict_id=f"conflict_distance_{day.isoformat()}",
                    type="DISTANCE_EXCESSIVE",
                    severity="ERROR",
                    scope="DAY",
                    message=(
                        f"{day.isoformat()} 移动 {travel} 分钟，"
                        f"与「{'、'.join(profile.mobility_constraints)}」冲突。"
                    ),
                    affected_node_ids=[item.node_id for item in items],
                    repair_options=[
                        RepairOption(
                            repair_option_id=f"repair_mode_{day.isoformat()}",
                            action="CHANGE_TRAVEL_MODE",
                            description="改用更省力的交通方式，或换成更近的地点。",
                            affected_node_ids=[item.node_id for item in items],
                        )
                    ],
                    status="OPEN",
                )
            )
    return conflicts


def _check_data_gaps(
    prior_conflicts: Sequence[Conflict], run_mode: RunMode
) -> list[Conflict]:
    """§14 不变量 3：`UNKNOWN` 关键事实阻止 VERIFIED 模式发布。"""

    conflicts: list[Conflict] = []
    for item in prior_conflicts:
        if item.type != "DATA_UNKNOWN":
            continue
        if run_mode is RunMode.VERIFIED:
            conflicts.append(
                Conflict(
                    conflict_id=f"{item.conflict_id}_verified",
                    type="DATA_UNKNOWN",
                    severity="ERROR",
                    scope=item.scope,
                    message=f"VERIFIED 模式下不允许未知关键事实：{item.message}",
                    affected_node_ids=list(item.affected_node_ids),
                    status="OPEN",
                )
            )
        else:
            conflicts.append(
                Conflict(
                    conflict_id=item.conflict_id,
                    type="DATA_UNKNOWN",
                    severity="WARNING",
                    scope=item.scope,
                    message=item.message,
                    affected_node_ids=list(item.affected_node_ids),
                    status="OPEN",
                )
            )
    return conflicts


def _parse_moment(raw: str | None) -> time | None:
    if not raw:
        return None
    try:
        hour, minute = raw.split(":")
        return time(int(hour), int(minute))
    except ValueError:
        return None


def _node_minutes(node: PlanNode) -> int:
    return int((node.end_at - node.start_at).total_seconds() // 60)
