"""会话服务：把存储、LangGraph 工作流和回复组装串起来（v0.4 契约）。

API 层只调用本服务，不直接接触图或存储实现。
"""

from __future__ import annotations

import uuid
from typing import Callable, Mapping, Sequence

from app.graph.workflow import run_turn
from app.schemas import (
    Conflict,
    ItineraryPlan,
    PlanState,
    PlanValidationStatus,
    RunMode,
    SendMessageData,
    TravelGuide,
    UserAction,
    VersionLineage,
    WarningItem,
)
from app.services.guide_service import (
    GuideDataError,
    fetch_preparation_rules,
    find_guide,
    store_guide,
)
from app.services.guide_service import build_guide as build_travel_guide
from app.services.plan_validator import attach_validation, validate_plan
from app.services.repair_engine import (
    apply_user_action,
    detect_incident,
    replan_for_incident,
)

from .reply_builder import build_name_lookup, build_reply, build_warnings
from .session_store import (
    ExcludedResourceRecord,
    SessionExtras,
    SessionRepository,
)


class ProfileVersionConflictError(Exception):
    """调用方持有的 `expected_profile_version` 与当前版本不一致。"""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected_profile_version={expected}，当前={actual}")
        self.expected = expected
        self.actual = actual


class GuideNotFoundError(KeyError):
    """请求的攻略不存在。"""


class GuideNotReadyError(Exception):
    """还没有通过验证的计划，或组装素材缺失，因此给不出攻略。"""

    def __init__(self, message: str, *, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing = list(missing or [])


class GuideVersionConflictError(Exception):
    """调用方持有的 `expected_guide_version` 与当前版本不一致。"""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected_guide_version={expected}，当前={actual}")
        self.expected = expected
        self.actual = actual


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        graph,
        *,
        known_destinations: Mapping[str, str] | None = None,
        data_is_mock: bool = True,
        mcp=None,
    ) -> None:
        self._repository = repository
        self._graph = graph
        self._mcp = mcp
        self._known_destinations = dict(known_destinations or {})
        self._data_is_mock = data_is_mock
        self._name_lookup: Callable[[str], str | None] = build_name_lookup(
            self._known_destinations
        )

    def create_session(
        self, session_id: str | None = None, run_mode: RunMode = RunMode.DEMO
    ) -> PlanState:
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        return self._repository.create(session_id, run_mode)

    def send_message(
        self,
        session_id: str,
        text: str,
        expected_profile_version: int | None = None,
    ) -> tuple[PlanState, SendMessageData, list[WarningItem]]:
        state = self._repository.get(session_id)
        extras = self._repository.get_extras(session_id)

        current_version = extras.profile.profile_version if extras.profile else None
        if (
            expected_profile_version is not None
            and current_version is not None
            and expected_profile_version != current_version
        ):
            raise ProfileVersionConflictError(expected_profile_version, current_version)

        new_state, context = run_turn(
            self._graph,
            state,
            text,
            draft=extras.draft,
            profile=extras.profile,
            previous_plan=extras.current_plan,
            run_mode=extras.run_mode,
        )
        extras.draft = context.draft
        extras.profile = context.profile
        extras.excluded_resources = _excluded_records(context)
        outcome = context.plan_outcome
        if outcome is not None:
            extras.current_plan = context.validated_plan or outcome.plan
            extras.data_snapshot = outcome.data_snapshot
            extras.intercity_options = list(outcome.intercity_options)
            extras.plan_conflicts = list(
                context.validation_result.conflicts
                if context.validation_result is not None
                else outcome.conflicts
            )
            extras.plan_missing_inputs = list(outcome.missing_inputs)
        if context.repair_outcome is not None and context.repair_outcome.lineage is not None:
            extras.version_lineage = context.repair_outcome.lineage
        if context.validated_plan is not None:
            extras.current_plan = context.validated_plan
        if context.validation_result is not None:
            extras.plan_conflicts = list(context.validation_result.conflicts)
        guide_notes: list[str] = []
        if context.guide_outcome is not None:
            if context.guide_outcome.guide is not None:
                store_guide(extras, context.guide_outcome.guide)
            else:
                guide_notes = [
                    f"攻略暂时组装不了：{note}" for note in context.guide_outcome.notes
                ]

        self._repository.save(new_state)
        self._repository.save_extras(session_id, extras)

        reply = build_reply(
            new_state,
            draft=extras.draft,
            profile=extras.profile,
            recommendations=context.recommendations,
            filter_result=context.filter_result,
            plan=extras.current_plan,
            plan_conflicts=extras.plan_conflicts,
            missing_inputs=extras.plan_missing_inputs,
            guide_id=extras.current_guide_id,
            guide_notes=guide_notes,
            name_lookup=self._name_lookup,
            data_is_mock=self._data_is_mock,
        )
        warnings = build_warnings(
            new_state, draft=extras.draft, data_is_mock=self._data_is_mock
        )
        return new_state, reply, warnings

    def get_state(
        self, session_id: str
    ) -> tuple[PlanState, SendMessageData, list[WarningItem]]:
        state = self._repository.get(session_id)
        extras = self._repository.get_extras(session_id)
        reply = build_reply(
            state,
            draft=extras.draft,
            profile=extras.profile,
            plan=extras.current_plan,
            plan_conflicts=extras.plan_conflicts,
            missing_inputs=extras.plan_missing_inputs,
            # 刷新页面时也要能拿到攻略 ID，否则前端会从"有攻略"退回"没生成"
            guide_id=extras.current_guide_id,
            name_lookup=self._name_lookup,
            data_is_mock=self._data_is_mock,
        )
        warnings = build_warnings(
            state, draft=extras.draft, data_is_mock=self._data_is_mock
        )
        return state, reply, warnings


    # --- C7：攻略接口 -------------------------------------------------------

    def get_guide(self, guide_id: str, version: int | None = None) -> TravelGuide:
        """按攻略 ID 取攻略（可选指定版本）。"""

        for session_id in self._repository.session_ids():
            found = find_guide(self._repository.get_extras(session_id), guide_id, version)
            if found is not None:
                return found
        raise GuideNotFoundError(guide_id)

    def confirm_guide(
        self,
        guide_id: str,
        *,
        expected_guide_version: int,
        lock_node_ids: Sequence[str] = (),
        idempotency_key: str | None = None,
    ) -> TravelGuide:
        """确认攻略：锁定指定节点（此后自动修复不得修改），并生成新攻略版本。"""

        session_id = self._session_of(guide_id)
        extras = self._repository.get_extras(session_id)
        current = find_guide(extras, guide_id)
        if current is None:
            raise GuideNotFoundError(guide_id)
        if idempotency_key and idempotency_key in extras.handled_idempotency_keys:
            # 同一个幂等键重复提交：返回上次结果，不再升版本
            replay = find_guide(
                extras, guide_id, extras.handled_idempotency_keys[idempotency_key]
            )
            if replay is not None:
                return replay
        if expected_guide_version != current.guide_version:
            raise GuideVersionConflictError(expected_guide_version, current.guide_version)

        locked = sorted({*lock_node_ids})
        if locked and extras.current_plan is not None:
            nodes = [
                node.model_copy(update={"locked": True})
                if node.node_id in set(locked)
                else node
                for node in extras.current_plan.nodes
            ]
            payload = extras.current_plan.model_dump()
            payload["nodes"] = [node.model_dump() for node in nodes]
            # 锁定只改状态、不改行程内容：计划版本不变，攻略版本递增
            extras.current_plan = ItineraryPlan.model_validate(payload)
        state = self._repository.get(session_id)
        self._repository.save(
            state.model_copy(update={"locked_node_ids": sorted({*state.locked_node_ids, *locked})})
        )
        guide = self._build_guide(
            extras,
            lifecycle_status="CONFIRMED",
            guide_version=current.guide_version + 1,
            parent_guide_version=current.guide_version,
        )
        if idempotency_key:
            extras.handled_idempotency_keys[idempotency_key] = guide.guide_version
        self._repository.save_extras(session_id, extras)
        return guide

    def modify_guide(
        self, guide_id: str, action: UserAction
    ) -> tuple[TravelGuide, VersionLineage | None, list[Conflict], list[str]]:
        """执行用户的显式修改（`MODIFY_GUIDE`）或突发事件（`REPORT_INCIDENT`）。"""

        session_id = self._session_of(guide_id)
        extras = self._repository.get_extras(session_id)
        current = find_guide(extras, guide_id)
        if current is None:
            raise GuideNotFoundError(guide_id)
        key = action.idempotency_key
        if key and key in extras.handled_idempotency_keys:
            replay = find_guide(
                extras, guide_id, extras.handled_idempotency_keys[key]
            )
            if replay is not None:
                return replay, extras.version_lineage, list(extras.plan_conflicts), [
                    "该请求此前已处理（幂等键命中），返回同一结果。"
                ]
        if (
            action.expected_guide_version is not None
            and action.expected_guide_version != current.guide_version
        ):
            raise GuideVersionConflictError(
                action.expected_guide_version, current.guide_version
            )
        plan = extras.current_plan
        profile = extras.profile
        if plan is None or profile is None:
            raise GuideNotReadyError("会话里还没有可修改的计划。")
        destination_id = plan.trip_segments[0].destination_id
        candidates = self._fetch_candidates(profile, destination_id)

        if action.action_type == "REPORT_INCIDENT":
            trigger = detect_incident(action.raw_text or "")
            if trigger is None:
                raise GuideNotReadyError("没有识别到突发事件，请说明发生了什么（例如「下雨了」）。")
            outcome = replan_for_incident(
                plan,
                incident_type=trigger,
                profile=profile,
                candidates=candidates,
                mcp=self._mcp,
                locked_node_ids=self._repository.get(session_id).locked_node_ids,
                intercity_options=self._intercity(profile, destination_id, extras),
                change_request_id=action.action_id,
                run_mode=extras.run_mode,
            )
        else:
            payload = action.payload
            if payload is None:
                raise GuideNotReadyError("修改请求缺少 payload（改动内容）。")
            outcome = apply_user_action(
                plan,
                change_type=payload.change_type,
                target_node_ids=payload.target_node_ids,
                profile=profile,
                candidates=candidates,
                mcp=self._mcp,
                locked_node_ids=self._repository.get(session_id).locked_node_ids,
                intercity_options=self._intercity(profile, destination_id, extras),
                change_request_id=action.action_id,
                run_mode=extras.run_mode,
            )
        if outcome.plan is None:
            # 改不动就如实报，不返回"看起来成功"的空结果
            raise GuideNotReadyError(
                outcome.notes[0] if outcome.notes else "该修改暂时无法自动完成。",
                missing=[item.conflict_id for item in outcome.unresolved],
            )

        result = validate_plan(
            outcome.plan,
            profile=profile,
            candidates=candidates,
            prior_conflicts=outcome.unresolved,
            run_mode=extras.run_mode,
        )
        extras.current_plan = attach_validation(outcome.plan, result)
        extras.plan_conflicts = list(result.conflicts)
        extras.version_lineage = outcome.lineage
        state = self._repository.get(session_id)
        self._repository.save(
            state.model_copy(
                update={
                    "current_plan_id": extras.current_plan.plan_id,
                    "current_plan_version": extras.current_plan.plan_version,
                    "conflict_ids": [item.conflict_id for item in result.conflicts],
                    "repair_attempts": state.repair_attempts + 1,
                }
            )
        )
        guide = self._build_guide(
            extras,
            lifecycle_status=current.lifecycle_status,
            guide_version=current.guide_version + 1,
            parent_guide_version=current.guide_version,
        )
        # 版本谱系要带攻略版本号，否则前端显示不了"攻略 v2 → v3"
        lineage = outcome.lineage
        if lineage is not None:
            lineage = lineage.model_copy(
                update={
                    "parent_guide_version": current.guide_version,
                    "new_guide_version": guide.guide_version,
                }
            )
            extras.version_lineage = lineage
        if key:
            extras.handled_idempotency_keys[key] = guide.guide_version
        self._repository.save_extras(session_id, extras)
        return guide, lineage, list(result.conflicts), list(outcome.notes)

    # --- 攻略组装的素材准备 -------------------------------------------------

    def _build_guide(
        self,
        extras: SessionExtras,
        *,
        lifecycle_status: str,
        guide_version: int,
        parent_guide_version: int | None,
    ) -> TravelGuide:
        if self._mcp is None:
            raise GuideNotReadyError("没有装配 MCP Provider，无法组装攻略。")
        plan = extras.current_plan
        profile = extras.profile
        if plan is None or profile is None:
            raise GuideNotReadyError("会话里还没有可用的计划。")
        if plan.plan_validation_status != PlanValidationStatus.VALID:
            raise GuideNotReadyError("计划尚未通过验证，不能生成攻略。")
        destination_id = plan.trip_segments[0].destination_id
        candidates = self._fetch_candidates(profile, destination_id)
        evidence = self._evidence(destination_id)
        outcome = build_travel_guide(
            plan=plan,
            profile=profile,
            candidates=candidates,
            intercity_options=self._intercity(profile, destination_id, extras),
            mcp=self._mcp,
            evidence=evidence,
            preparation_rules=fetch_preparation_rules(
                profile,
                self._mcp,
                activity_tags=profile.interests,
                destination_id=destination_id,
            ),
            conflicts=extras.plan_conflicts,
            data_snapshot=extras.data_snapshot,
            destination_names={
                destination_id: self._name_lookup(destination_id) or destination_id
            },
            run_mode=extras.run_mode,
            lifecycle_status=lifecycle_status,
            guide_id=extras.current_guide_id,
            guide_version=guide_version,
            parent_guide_version=parent_guide_version,
        )
        if outcome.guide is None:
            raise GuideNotReadyError(
                outcome.notes[0] if outcome.notes else "组装攻略的素材不足。",
                missing=outcome.missing_inputs,
            )
        store_guide(extras, outcome.guide)
        state = self._repository.get(outcome.guide.session_id)
        self._repository.save(
            state.model_copy(
                update={
                    "current_guide_id": outcome.guide.guide_id,
                    "current_guide_version": outcome.guide.guide_version,
                }
            )
        )
        return outcome.guide

    def _session_of(self, guide_id: str) -> str:
        for session_id in self._repository.session_ids():
            if find_guide(self._repository.get_extras(session_id), guide_id) is not None:
                return session_id
        raise GuideNotFoundError(guide_id)

    def _fetch_candidates(self, profile, destination_id: str):
        from app.schemas import DateRange, SearchResourcesRequest

        date_range = DateRange(start_date=profile.start_date, end_date=profile.end_date)
        resources = []
        for resource_type in ("VISIT_PLACE", "RESTAURANT", "LODGING", "LODGING_AREA"):
            output = self._mcp.search_resources(
                SearchResourcesRequest(
                    resource_type=resource_type,
                    destination_id=destination_id,
                    date_range=date_range,
                )
            )
            resources.extend(output.resources)
        return resources

    def _evidence(self, destination_id: str):
        from app.schemas import SearchTravelKnowledgeRequest

        try:
            output = self._mcp.search_travel_knowledge(
                SearchTravelKnowledgeRequest(
                    query="目的地认知与体验特点",
                    destination_ids=[destination_id],
                    top_k=10,
                )
            )
        except Exception:
            return []
        return list(output.evidence)

    def _intercity(self, profile, destination_id: str, extras: SessionExtras):
        from app.services.itinerary_planner import fetch_intercity_options

        if extras.intercity_options:
            return list(extras.intercity_options)
        return fetch_intercity_options(profile, destination_id, self._mcp, [])


def _excluded_records(context) -> list[ExcludedResourceRecord]:
    """把本轮前置过滤排除的资源整理成可持久化的记录。"""

    result = context.filter_result
    if result is None:
        return []
    return [
        ExcludedResourceRecord(
            resource_id=item.resource_id,
            status=item.status,
            reason=item.reason,
            unavailable_dates=result.unavailable_dates.get(item.resource_id, []),
        )
        for item in result.excluded
    ]
