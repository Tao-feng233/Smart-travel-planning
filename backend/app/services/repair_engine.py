"""C6 修复与重规划：把"计划 + 问题"变成"新版本计划"。

契约依据：

* `CONTRACTS.md` §10.1 `VersionLineage`（保留/变更/移除节点 + 替换关系）；
* §10.3 通用重规划流程（**不同事件走同一套机制**，不建互相独立的重规划系统）；
* §8.1 `RepairOption.action`（本模块只实现其中能自动化、且不需要用户授权的动作）；
* §14 不变量 6/7：锁定节点不得被静默修改；每次成功修改都生成新计划版本。

两个入口，同一套内核：

```text
repair_plan()          自动修复：喂进 C5 的冲突 → 产出 v2（能修的修，不能修的原样返回）
replan_for_incident()  突发重规划：下雨 / 闭馆 / 起晚等事件 → 只重排受影响的那一天
```

**不做的事**（守住"不得自动突破"的边界）：

* 锁定节点（`locked_node_ids`）与已完成节点（`completed_node_ids`）一律不动，
  相关冲突改为返回给用户决定；
* 不会为了让计划"过验证"而编造路线、价格或开放时间；缺数据的部分继续记为
  `DATA_UNKNOWN`；
* 固定预算（`budget_flexibility = FIXED`）不会被自动放宽。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Sequence

from app.schemas import (
    Conflict,
    CostItem,
    DayPlan,
    IntercityOption,
    ItineraryPlan,
    LodgingCandidate,
    PlanNode,
    PlanValidationStatus,
    ReplacementRelation,
    ResourceCandidateBase,
    RestaurantCandidate,
    RunMode,
    TravelLeg,
    TripProfile,
    VersionLineage,
    VisitPlaceCandidate,
)
from app.services.availability_filter import TripFilterResult
from app.services.itinerary_planner import (
    build_travel_leg,
    collect_costs,
    make_plan_node,
    summarize_budget,
)
from app.services.plan_validator import ValidationResult, validate_plan

#: 事件类型（与 `AlternativePlan.trigger` 的取值对齐）
INCIDENT_TRIGGERS = (
    "RAIN",
    "LATE_START",
    "CLOSURE",
    "CROWD",
    "USER_TIRED",
    "RESTAURANT_UNAVAILABLE",
)

#: 事件关键词 → 触发类型（规则式；B5 的 `ActionInterpreter` 接入后由它来判定）
_INCIDENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("RAIN", ("下雨", "雨天", "暴雨", "下大雨")),
    ("CLOSURE", ("闭馆", "关门", "没开门", "临时关闭", "不开放")),
    ("CROWD", ("人太多", "排队太长", "排不上")),
    ("USER_TIRED", ("累了", "走不动", "太累", "体力不支")),
    ("LATE_START", ("起晚了", "睡过头", "没赶上", "出发晚了")),
)


@dataclass
class RepairOutcome:
    """修复结果：新计划 + 版本谱系 + 说明；修不动时 `plan` 为 None。"""

    plan: ItineraryPlan | None = None
    lineage: VersionLineage | None = None
    applied: list[str] = field(default_factory=list)
    unresolved: list[Conflict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    validation: ValidationResult | None = None


def detect_incident(text: str) -> str | None:
    """从用户这句话里识别突发事件类型；识别不到返回 None。"""

    for trigger, words in _INCIDENT_KEYWORDS:
        if any(word in text for word in words):
            return trigger
    return None


def apply_user_action(
    plan: ItineraryPlan,
    *,
    change_type: str,
    target_node_ids: Sequence[str],
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase],
    mcp,
    filter_result: TripFilterResult | None = None,
    locked_node_ids: Sequence[str] = (),
    completed_node_ids: Sequence[str] = (),
    intercity_options: Sequence[IntercityOption] = (),
    change_request_id: str | None = None,
    run_mode: RunMode = RunMode.DEMO,
) -> RepairOutcome:
    """执行用户的显式修改动作（C7 的 `/api/guides/{id}/modify`）。

    P0 只支持两种能确定性执行、且不替用户做决定的动作：

    ```text
    REPLACE_NODE  把指定节点换成同日可用的替代资源
    REMOVE_NODE   删掉指定节点（用户明确要求，不是系统自动删）
    ```

    其余 change_type（改日期 / 改预算 / 降强度 / 换住宿等）需要重新排程或改画像，
    属于 P1，这里**明确报不支持**，不假装做了。
    """

    if change_type not in ("REPLACE_NODE", "REMOVE_NODE"):
        return RepairOutcome(
            notes=[f"P0 暂不支持该修改动作：{change_type}（需要重新排程，属于 P1）。"],
        )
    protected = {*locked_node_ids, *completed_node_ids}
    targets = [node_id for node_id in target_node_ids if node_id not in protected]
    if not targets:
        return RepairOutcome(
            notes=["目标节点不存在、或已被锁定/已完成，未做任何修改。"],
        )

    nodes = {node.node_id: node for node in plan.nodes}
    days = {day.date: day for day in plan.days}
    stay = plan.stay_segments[0] if plan.stay_segments else None
    lodging = _lodging_of(plan, candidates)
    relations: list[ReplacementRelation] = []
    removed: list[str] = []
    changed: list[str] = []
    applied: list[str] = []
    touched: set[date] = set()

    for node_id in targets:
        node = nodes.get(node_id)
        if node is None:
            continue
        day = node.start_at.date()
        if change_type == "REMOVE_NODE":
            days[day] = days[day].model_copy(
                update={"node_ids": [item for item in days[day].node_ids if item != node_id]}
            )
            nodes.pop(node_id, None)
            removed.append(node_id)
            applied.append(f"按用户要求删除节点 {node_id}")
            touched.add(day)
            continue
        replacement = _pick_replacement(
            node,
            day,
            candidates,
            plan_nodes=list(nodes.values()),
            filter_result=filter_result,
        )
        if replacement is None:
            continue
        relation = _swap_resource(node, replacement, nodes, days)
        relations.append(relation)
        removed.append(relation.old_node_id)
        changed.append(relation.new_node_id)
        applied.append(f"{relation.old_node_id} → {relation.new_node_id}")
        touched.add(day)

    if not applied:
        return RepairOutcome(
            notes=[f"没有找到可用的替代资源（动作 {change_type}）。"],
        )
    return _rebuild(
        plan,
        nodes=list(nodes.values()),
        days=days,
        touched_days=touched,
        profile=profile,
        candidates=candidates,
        mcp=mcp,
        lodging=lodging,
        stay=stay,
        intercity_options=intercity_options,
        relations=relations,
        removed_ids=removed,
        changed_ids=changed,
        applied=applied,
        unresolved=[],
        change_request_id=change_request_id or f"change_{uuid.uuid4().hex[:8]}",
        run_mode=run_mode,
        notes=["已按用户要求修改，其他安排保持原样。"],
    )


# --- 入口 1：自动修复 -------------------------------------------------------


def repair_plan(
    plan: ItineraryPlan,
    conflicts: Sequence[Conflict],
    *,
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase],
    mcp,
    filter_result: TripFilterResult | None = None,
    locked_node_ids: Sequence[str] = (),
    completed_node_ids: Sequence[str] = (),
    intercity_options: Sequence[IntercityOption] = (),
    change_request_id: str | None = None,
    run_mode: RunMode = RunMode.DEMO,
) -> RepairOutcome:
    """按 C5 给出的冲突尝试自动修复；只做不需要用户授权的动作。"""

    protected = {*locked_node_ids, *completed_node_ids}
    nodes = {node.node_id: node for node in plan.nodes}
    days = {day.date: day for day in plan.days}
    stay = plan.stay_segments[0] if plan.stay_segments else None
    lodging = _lodging_of(plan, candidates)
    applied: list[str] = []
    unresolved: list[Conflict] = []
    relations: list[ReplacementRelation] = []
    removed: list[str] = []
    changed: list[str] = []
    touched_days: set[date] = set()

    for conflict in conflicts:
        if conflict.severity != "ERROR":
            continue
        if any(node_id in protected for node_id in conflict.affected_node_ids):
            unresolved.append(conflict)
            continue
        if conflict.type == "OPENING_HOURS" and conflict.conflict_id.startswith(
            "conflict_unavailable_"
        ):
            handled = _replace_unavailable_node(
                conflict, nodes, days, candidates, filter_result, protected
            )
        elif conflict.type == "OPENING_HOURS":
            handled = _shift_into_opening_hours(conflict, nodes, days, candidates)
        elif conflict.type == "TIME_WINDOW":
            handled = _fix_time_window(conflict, nodes, days)
        elif conflict.type == "BUDGET_EXCEEDED":
            handled = _cut_cost(conflict, plan, candidates, profile)
        else:
            handled = None
        if handled is None:
            unresolved.append(conflict)
            continue
        applied.append(handled[0])
        if handled[1] is not None:
            relations.append(handled[1])
            removed.append(handled[1].old_node_id)
            changed.append(handled[1].new_node_id)
        if handled[3] is not None:
            stay = handled[3]
        touched_days.update(handled[2])

    if not applied:
        return RepairOutcome(
            plan=None,
            unresolved=list(conflicts),
            notes=["没有可自动修复的问题，需要用户决定。"],
        )

    return _rebuild(
        plan,
        nodes=list(nodes.values()),
        days=days,
        touched_days=touched_days,
        profile=profile,
        candidates=candidates,
        mcp=mcp,
        lodging=lodging,
        stay=stay,
        intercity_options=intercity_options,
        relations=relations,
        removed_ids=removed,
        changed_ids=changed,
        applied=applied,
        unresolved=unresolved,
        change_request_id=change_request_id or f"change_{uuid.uuid4().hex[:8]}",
        run_mode=run_mode,
        notes=[],
    )


# --- 入口 2：突发重规划 -----------------------------------------------------


def replan_for_incident(
    plan: ItineraryPlan,
    *,
    incident_type: str,
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase],
    mcp,
    affected_date: date | None = None,
    filter_result: TripFilterResult | None = None,
    locked_node_ids: Sequence[str] = (),
    completed_node_ids: Sequence[str] = (),
    intercity_options: Sequence[IntercityOption] = (),
    change_request_id: str | None = None,
    run_mode: RunMode = RunMode.DEMO,
) -> RepairOutcome:
    """只重排受事件影响的那一天，其余安排与锁定节点原样保留（§10.3）。"""

    if incident_type not in INCIDENT_TRIGGERS:
        return RepairOutcome(notes=[f"未知事件类型：{incident_type}"])

    protected = {*locked_node_ids, *completed_node_ids}
    day = affected_date or min(item.date for item in plan.days)
    nodes = {node.node_id: node for node in plan.nodes}
    days = {item.date: item for item in plan.days}
    day_plan = days[day]
    stay = plan.stay_segments[0] if plan.stay_segments else None
    lodging = _lodging_of(plan, candidates)

    relations: list[ReplacementRelation] = []
    removed: list[str] = []
    changed: list[str] = []
    applied: list[str] = []
    unresolved: list[Conflict] = []
    used_ids = {item.resource_id for item in plan.nodes if item.resource_id}

    for node_id in day_plan.node_ids:
        node = nodes[node_id]
        if node_id in protected:
            # 已完成 / 已锁定：不静默修改（§14 不变量 6）
            continue
        if incident_type == "RAIN" and not _is_outdoor(node, candidates):
            continue
        if incident_type == "USER_TIRED" and node.node_type != "ATTRACTION":
            continue
        replacement = _pick_replacement(
            node,
            day,
            candidates,
            plan_nodes=list(nodes.values()),
            filter_result=filter_result,
            indoor_only=incident_type in ("RAIN", "USER_TIRED"),
        )
        if replacement is None:
            unresolved.append(
                Conflict(
                    conflict_id=f"conflict_incident_{node_id}",
                    type="WEATHER_UNSUITABLE"
                    if incident_type == "RAIN"
                    else "DATA_UNKNOWN",
                    severity="WARNING",
                    scope="NODE",
                    message=(
                        f"{day.isoformat()} 没有合适的替代安排（{incident_type}），"
                        "需要用户决定：换日期、跳过或保留原计划。"
                    ),
                    affected_node_ids=[node_id],
                    status="OPEN",
                )
            )
            continue

        new_node = node.model_copy(
            update={
                "node_id": f"node_{uuid.uuid4().hex[:8]}",
                "resource_id": replacement.resource_id,
                "reason": (
                    f"因{_trigger_label(incident_type)}换成 {replacement.name}"
                    f"（原 {node.resource_id}）。"
                ),
                "evidence_ids": list(replacement.evidence_ids),
            }
        )
        nodes[new_node.node_id] = new_node
        day_plan = day_plan.model_copy(
            update={
                "node_ids": [
                    new_node.node_id if item == node_id else item
                    for item in day_plan.node_ids
                ]
            }
        )
        days[day] = day_plan
        used_ids.add(replacement.resource_id)
        relations.append(
            ReplacementRelation(old_node_id=node_id, new_node_id=new_node.node_id)
        )
        removed.append(node_id)
        changed.append(new_node.node_id)
        applied.append(f"把 {node.resource_id} 换成 {replacement.resource_id}")
        nodes.pop(node_id, None)

    if not applied:
        return RepairOutcome(
            plan=None,
            unresolved=unresolved,
            notes=[f"{day.isoformat()} 没有需要调整的安排。"],
        )

    return _rebuild(
        plan,
        nodes=list(nodes.values()),
        days=days,
        touched_days={day},
        profile=profile,
        candidates=candidates,
        mcp=mcp,
        lodging=lodging,
        stay=stay,
        intercity_options=intercity_options,
        relations=relations,
        removed_ids=removed,
        changed_ids=changed,
        applied=applied,
        unresolved=unresolved,
        change_request_id=change_request_id or f"change_{uuid.uuid4().hex[:8]}",
        run_mode=run_mode,
        notes=[f"只重排了 {day.isoformat()}，其余日期与锁定节点保持原样。"],
    )


# --- 修复动作 ---------------------------------------------------------------


def _replace_unavailable_node(
    conflict: Conflict,
    nodes: dict[str, PlanNode],
    days: dict[date, DayPlan],
    candidates: Sequence[ResourceCandidateBase],
    filter_result: TripFilterResult | None,
    protected: set[str],
):
    node = nodes.get(conflict.affected_node_ids[0]) if conflict.affected_node_ids else None
    if node is None:
        return None
    day = node.start_at.date()
    replacement = _pick_replacement(
        node,
        day,
        candidates,
        plan_nodes=list(nodes.values()),
        filter_result=filter_result,
    )
    if replacement is None:
        return None
    return (
        f"替换 {node.resource_id}",
        _swap_resource(node, replacement, nodes, days),
        {day},
        None,
    )


def _swap_resource(
    node: PlanNode,
    replacement: ResourceCandidateBase,
    nodes: dict[str, PlanNode],
    days: dict[date, DayPlan],
) -> ReplacementRelation:
    """用新资源生成新节点（新 ID），并把当天引用改过去 + 记录替换关系。"""

    new_node = node.model_copy(
        update={
            "node_id": f"node_{uuid.uuid4().hex[:8]}",
            "resource_id": replacement.resource_id,
            "reason": f"改为 {replacement.name}（原节点 {node.node_id} 不可用）。",
            "evidence_ids": list(replacement.evidence_ids),
        }
    )
    nodes[new_node.node_id] = new_node
    day = node.start_at.date()
    day_plan = days[day]
    days[day] = day_plan.model_copy(
        update={
            "node_ids": [
                new_node.node_id if item == node.node_id else item
                for item in day_plan.node_ids
            ]
        }
    )
    nodes.pop(node.node_id, None)
    return ReplacementRelation(old_node_id=node.node_id, new_node_id=new_node.node_id)


def _shift_into_opening_hours(
    conflict: Conflict,
    nodes: dict[str, PlanNode],
    days: dict[date, DayPlan],
    candidates: Sequence[ResourceCandidateBase],
):
    node = nodes.get(conflict.affected_node_ids[0]) if conflict.affected_node_ids else None
    if node is None:
        return None
    resource = _resource_of(candidates, node.resource_id)
    windows = getattr(resource, "opening_windows", None) if resource else None
    if not windows:
        return None
    window = windows[0]
    day = node.start_at.date()
    duration = node.end_at - node.start_at
    new_start = max(
        node.start_at,
        datetime.combine(day, window.start_at.time(), tzinfo=node.start_at.tzinfo),
    )
    if new_start + duration > datetime.combine(
        day, window.end_at.time(), tzinfo=node.start_at.tzinfo
    ):
        return None
    moved = node.model_copy(update={"start_at": new_start, "end_at": new_start + duration})
    nodes[node.node_id] = moved
    return f"把 {node.node_id} 挪进开放时间", None, {day}, None


def _fix_time_window(
    conflict: Conflict,
    nodes: dict[str, PlanNode],
    days: dict[date, DayPlan],
):
    """重叠冲突：把靠后的节点顺推到前一个节点结束之后。"""

    if len(conflict.affected_node_ids) < 2:
        return None
    first, second = (nodes.get(item) for item in conflict.affected_node_ids[:2])
    if first is None or second is None:
        return None
    duration = second.end_at - second.start_at
    new_start = max(second.start_at, first.end_at)
    nodes[second.node_id] = second.model_copy(
        update={"start_at": new_start, "end_at": new_start + duration}
    )
    return f"顺推 {second.node_id} 避免重叠", None, {second.start_at.date()}, None


def _cut_cost(
    conflict: Conflict,
    plan: ItineraryPlan,
    candidates: Sequence[ResourceCandidateBase],
    profile: TripProfile,
):
    """超预算：先尝试换更便宜的住宿；不行就交回用户（不自动放宽预算）。"""

    current = _lodging_of(plan, candidates)
    options = [item for item in candidates if isinstance(item, LodgingCandidate)]
    cheaper = [
        item
        for item in options
        if current is None or _min_price(item) < _min_price(current)
    ]
    if not cheaper:
        return None
    best = sorted(cheaper, key=_min_price)[0]
    stay = plan.stay_segments[0].model_copy(
        update={"lodging_id": best.resource_id, "lodging_area": best.lodging_area}
    )
    return f"住宿改为更便宜的 {best.resource_id}", None, set(), stay


# --- 组装新版本 -------------------------------------------------------------


def _rebuild(
    plan: ItineraryPlan,
    *,
    nodes: list[PlanNode],
    days: dict[date, DayPlan],
    touched_days: set[date],
    profile: TripProfile,
    candidates: Sequence[ResourceCandidateBase],
    mcp,
    lodging: LodgingCandidate | None,
    stay,
    intercity_options: Sequence[IntercityOption],
    relations: list[ReplacementRelation],
    removed_ids: list[str],
    changed_ids: list[str],
    applied: list[str],
    unresolved: list[Conflict],
    change_request_id: str,
    run_mode: RunMode,
    notes: list[str],
) -> RepairOutcome:
    """重建计划：受影响的日子重算交通与费用，其余部分原样保留。"""

    node_map = {node.node_id: node for node in nodes}
    keep_legs = [
        leg
        for leg in plan.travel_legs
        if leg.depart_at.date() not in touched_days
    ]
    new_legs: list[TravelLeg] = []
    leg_costs: list[CostItem] = []
    extra_conflicts: list[Conflict] = []

    for day, day_plan in days.items():
        ordered = sorted(
            (node_map[node_id] for node_id in day_plan.node_ids if node_id in node_map),
            key=lambda item: item.start_at,
        )
        day_legs: list[TravelLeg] = []
        if day in touched_days:
            for previous, following in zip(ordered, ordered[1:]):
                leg, conflict, cost = build_travel_leg(
                    previous, following, mcp, len(new_legs) + 1, len(leg_costs) + 1
                )
                if leg is not None:
                    new_legs.append(leg)
                    day_legs.append(leg)
                if cost is not None:
                    leg_costs.append(cost)
                if conflict is not None:
                    extra_conflicts.append(conflict)
        else:
            day_legs = [
                leg
                for leg in plan.travel_legs
                if leg.depart_at.date() == day
            ]
        days[day] = day_plan.model_copy(
            update={"travel_leg_ids": [leg.leg_id for leg in day_legs]}
        )

    restaurants = [item for item in candidates if isinstance(item, RestaurantCandidate)]
    meals = len([item for item in nodes if item.node_type == "MEAL"])
    cost_items = collect_costs(
        profile=profile,
        leg_costs=leg_costs,
        stay_lodging=lodging,
        restaurants=restaurants,
        meal_count=meals,
        intercity_options=list(intercity_options),
    )
    new_version = plan.plan_version + 1
    all_legs = [*keep_legs, *new_legs]
    all_legs = [
        leg.model_copy(update={"leg_id": f"leg_{index:03d}"})
        for index, leg in enumerate(all_legs, 1)
    ]
    # 顺序按天排好，DayPlan 引用的 leg_id 也要跟着换
    per_day_legs: dict[date, list[str]] = {}
    for leg in all_legs:
        per_day_legs.setdefault(leg.depart_at.date(), []).append(leg.leg_id)
    for day, day_plan in list(days.items()):
        days[day] = day_plan.model_copy(
            update={"travel_leg_ids": per_day_legs.get(day, [])}
        )

    payload = plan.model_dump()
    payload.update(
        {
            "plan_version": new_version,
            "parent_plan_version": plan.plan_version,
            "nodes": [node.model_dump() for node in nodes],
            "days": [days[day].model_dump() for day in sorted(days)],
            "travel_legs": [
                leg.model_dump() for leg in all_legs
            ],
            "cost_items": [item.model_dump() for item in cost_items],
            "budget_summary": summarize_budget(cost_items, profile).model_dump(),
            # 修完还要再验证一次：状态先回到 PENDING，由 C5 决定 VALID/INVALID
            "plan_validation_status": PlanValidationStatus.PENDING,
            "conflict_ids": [],
        }
    )
    if stay is not None:
        payload["stay_segments"] = [stay.model_dump()]
    repaired = ItineraryPlan.model_validate(payload)
    validation = validate_plan(
        repaired,
        profile=profile,
        candidates=candidates,
        prior_conflicts=[*unresolved, *extra_conflicts],
        run_mode=run_mode,
    )
    # 修不动的问题必须继续暴露：不能因为"重建过一次"就把 ERROR 洗掉
    leftover = [item for item in unresolved if item.type != "DATA_UNKNOWN"]
    if leftover:
        validation.conflicts.extend(leftover)
        if any(item.severity == "ERROR" for item in validation.conflicts):
            validation.status = PlanValidationStatus.INVALID
    preserved = sorted(
        node_id
        for node_id in (node.node_id for node in plan.nodes)
        if node_id not in set(changed_ids) and node_id not in set(removed_ids)
    )
    lineage = VersionLineage(
        change_request_id=change_request_id,
        parent_plan_version=plan.plan_version,
        new_plan_version=new_version,
        preserved_node_ids=preserved,
        changed_node_ids=changed_ids,
        removed_node_ids=removed_ids,
        replacement_relations=relations,
    )
    return RepairOutcome(
        plan=repaired,
        lineage=lineage,
        applied=applied,
        unresolved=unresolved,
        notes=notes,
        validation=validation,
    )


# --- 小工具 -----------------------------------------------------------------


def _resource_of(
    candidates: Sequence[ResourceCandidateBase], resource_id: str | None
) -> ResourceCandidateBase | None:
    return next((item for item in candidates if item.resource_id == resource_id), None)


def _lodging_of(
    plan: ItineraryPlan, candidates: Sequence[ResourceCandidateBase]
) -> LodgingCandidate | None:
    if not plan.stay_segments:
        return None
    lodging_id = plan.stay_segments[0].lodging_id
    found = _resource_of(candidates, lodging_id)
    return found if isinstance(found, LodgingCandidate) else None


def _is_outdoor(node: PlanNode, candidates: Sequence[ResourceCandidateBase]) -> bool:
    resource = _resource_of(candidates, node.resource_id)
    if resource is None:
        return False
    indoor = getattr(resource, "indoor", None)
    sensitivity = getattr(resource, "weather_sensitivity", None)
    if indoor is None:
        return False
    return (not indoor) or sensitivity in ("MEDIUM", "HIGH")


def _pick_replacement(
    node: PlanNode,
    day: date,
    candidates: Sequence[ResourceCandidateBase],
    *,
    plan_nodes: Sequence[PlanNode],
    filter_result: TripFilterResult | None,
    indoor_only: bool = False,
) -> ResourceCandidateBase | None:
    """找同日可用、类型相符的替代资源（雨天只挑室内的）。

    两轮挑法：**先找整个行程都没用过的**，找不到再退一步允许"别的日子用过、
    但当天没用过"的资源。小数据集下如果只允许完全没用过的，闭馆替换会永远修不动
    （`poi_1..3` 全被排进 4 天行程里就是这样）。同一天内绝不重复。
    """

    blocked = dict(getattr(filter_result, "unavailable_dates", {}) or {})
    excluded = {
        item.resource_id for item in getattr(filter_result, "excluded", ()) or ()
    }
    used_anywhere = {item.resource_id for item in plan_nodes}
    used_today = {item.resource_id for item in plan_nodes if item.start_at.date() == day}
    want_meal = node.node_type == "MEAL"
    for rejected in (used_anywhere, used_today):
        for item in candidates:
            if item.resource_id in rejected or item.resource_id in excluded:
                continue
            if day in blocked.get(item.resource_id, ()):
                continue
            if item.availability_status == "UNAVAILABLE":
                continue
            if want_meal and not isinstance(item, RestaurantCandidate):
                continue
            if not want_meal and not isinstance(item, VisitPlaceCandidate):
                continue
            if indoor_only and not getattr(item, "indoor", False):
                continue
            return item
    return None


def _min_price(candidate: LodgingCandidate) -> float:
    money = candidate.price_range
    if money.amount is not None:
        return float(money.amount)
    return float(money.min_amount or 0.0)


def _trigger_label(trigger: str) -> str:
    return {
        "RAIN": "下雨",
        "CLOSURE": "临时闭馆",
        "CROWD": "人流过多",
        "USER_TIRED": "体力考虑",
        "LATE_START": "出发晚了",
        "RESTAURANT_UNAVAILABLE": "餐厅不可用",
    }.get(trigger, trigger)
