"""B5：把用户的修改指令翻译成 v0.4 的 `UserAction`。

⚠️ **当前后端没有接收 `UserAction` 的入口**：`ModifyGuideRequest` /
`GuideChangeData` 已在 `app/schemas/v04/rest.py` 定义，但攻略类路由属于 C7，尚未实现。
所以本轮交付「解析器 + 单测」，等 C7 落地后在路由里调用 `interpret()` 即可接线。

v0.4 与 v0.3 的差别（`handoff/B_交接说明.md`）：载体从 `ChangeRequest`
换成 `UserAction`，动作细节装在 `ActionChangePayload`
（`change_type` 8 种 / `scope_hint` 5 种 / `date` / `target_node_ids`）。

红线：`target_node_ids` 只能取自调用方给的已知节点清单；
越界 ID 一律丢弃 —— 否则后续重规划会拿着一个不存在的节点去改计划。
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from app.schemas import (
    ActionChangePayload,
    ActionType,
    ChangeType,
    ScopeHint,
    UserAction,
)

from .guards import normalize_choice
from .prompts import build_action_system_prompt, build_action_user_prompt
from .provider import LLMProvider

logger = logging.getLogger(__name__)

ACTION_TYPES: tuple[str, ...] = (
    "SELECT_DESTINATION",
    "CONFIRM_GUIDE",
    "MODIFY_GUIDE",
    "REPORT_INCIDENT",
)
CHANGE_TYPES: tuple[str, ...] = (
    "REMOVE_NODE",
    "REPLACE_NODE",
    "ADD_FIXED_NODE",
    "LOWER_INTENSITY",
    "CHANGE_DATE",
    "CHANGE_BUDGET",
    "CHANGE_PACE",
    "CHANGE_LODGING",
)
SCOPE_HINTS: tuple[str, ...] = (
    "NODE",
    "DAY",
    "STAY_SEGMENT",
    "TRIP_SEGMENT",
    "WHOLE_GUIDE",
)

#: 不需要 payload 的动作类型（契约里 `payload` 本身可空）
_PAYLOADLESS_ACTIONS = frozenset({"CONFIRM_GUIDE", "SELECT_DESTINATION"})

#: 规则式兜底的触发词表：**顺序即优先级**，越具体的表达放越前面。
_RULE_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CONFIRM_GUIDE", ("确认", "就这个", "就这样", "没问题", "可以了", "定了", "同意")),
    ("SELECT_DESTINATION", ("就选", "就它", "选这个")),
    (
        "CHANGE_DATE",
        ("改日期", "换日期", "改到", "改期", "推迟", "提前", "晚一天", "早一天", "延后"),
    ),
    ("CHANGE_PACE", ("节奏", "慢节奏", "快一点", "慢一点", "不赶")),
    ("LOWER_INTENSITY", ("太累", "轻松", "少安排", "减少", "减一点", "不想走太多", "休息")),
    ("CHANGE_LODGING", ("住宿", "酒店", "换个地方住", "住哪", "换住处")),
    ("CHANGE_BUDGET", ("预算", "太贵", "加点钱", "省钱", "便宜点")),
    ("REMOVE_NODE", ("去掉", "删掉", "删除", "取消", "不想去", "别去", "不要这个")),
    ("REPLACE_NODE", ("换成", "替换", "改成别的", "换个")),
    ("ADD_FIXED_NODE", ("加上", "新增", "增加一个", "还想", "补一个")),
)

_DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?")
#: 没有年份的月日表达（"10月3号""10/3"）。用户改行程时极少写年份，
#: 全靠用户在话里带上年份是判不出来的，需要用参考日期补年份。
_SHORT_DATE_RE = re.compile(r"(\d{1,2})[-/月](\d{1,2})[日号]")


class UserActionInterpreter(Protocol):
    """B5 的入口协议（供将来 C7 路由调用）。"""

    def interpret(
        self,
        *,
        session_id: str,
        text: str,
        known_node_ids: Sequence[str] = (),
        guide_id: str | None = None,
        expected_guide_version: int | None = None,
        idempotency_key: str | None = None,
        reference_date: date | None = None,
    ) -> UserAction: ...


@dataclass(frozen=True)
class InterpretedAction:
    """解析结果。`confident=False` 表示信息不足，调用方应再问用户一句。"""

    action: UserAction
    used_llm: bool
    confident: bool = True
    diagnostics: tuple[str, ...] = ()


# --- 规则式兜底 --------------------------------------------------------------


@dataclass
class RuleBasedUserActionInterpreter:
    """关键词兜底：模型不可用时仍能识别最常见的几类修改。

    它**不猜节点**：`target_node_ids` 永远留空，只给出 `change_type` 与
    `scope_hint`，并标 `confident=False`，让调用方决定是否再问一句。
    """

    def interpret(
        self,
        *,
        session_id: str,
        text: str,
        known_node_ids: Sequence[str] = (),
        guide_id: str | None = None,
        expected_guide_version: int | None = None,
        idempotency_key: str | None = None,
        reference_date: date | None = None,
    ) -> UserAction:
        message = (text or "").strip()
        action_type = "MODIFY_GUIDE"
        change_type: str | None = None

        for candidate_type, keywords in _RULE_TABLE:
            if any(keyword in message for keyword in keywords):
                if candidate_type in ("CONFIRM_GUIDE", "SELECT_DESTINATION"):
                    action_type = candidate_type
                else:
                    change_type = candidate_type
                break

        if action_type in _PAYLOADLESS_ACTIONS:
            return _build_action(
                session_id=session_id,
                action_type=action_type,
                payload=None,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                raw_text=message or None,
            )

        payload = ActionChangePayload(
            change_type=change_type or "REPLACE_NODE",
            scope_hint=_derive_scope(message, ()),
            date=_extract_date(message, reference_date),
            target_node_ids=[],
        )
        return _build_action(
            session_id=session_id,
            action_type="MODIFY_GUIDE",
            payload=payload,
            guide_id=guide_id,
            expected_guide_version=expected_guide_version,
            idempotency_key=idempotency_key,
            raw_text=message or None,
        )


# --- LLM 实现 ----------------------------------------------------------------


@dataclass
class LLMUserActionInterpreter:
    """LLM 版意图识别，失败时降级到关键词兜底。"""

    provider: LLMProvider
    fallback: UserActionInterpreter = field(default_factory=RuleBasedUserActionInterpreter)

    def interpret(
        self,
        *,
        session_id: str,
        text: str,
        known_node_ids: Sequence[str] = (),
        guide_id: str | None = None,
        expected_guide_version: int | None = None,
        idempotency_key: str | None = None,
        reference_date: date | None = None,
    ) -> UserAction:
        return self.interpret_with_diagnostics(
            session_id=session_id,
            text=text,
            known_node_ids=known_node_ids,
            reference_date=reference_date,
            guide_id=guide_id,
            expected_guide_version=expected_guide_version,
            idempotency_key=idempotency_key,
        ).action

    def interpret_with_diagnostics(
        self,
        *,
        session_id: str,
        text: str,
        known_node_ids: Sequence[str] = (),
        guide_id: str | None = None,
        expected_guide_version: int | None = None,
        idempotency_key: str | None = None,
        reference_date: date | None = None,
    ) -> InterpretedAction:
        message = (text or "").strip()
        node_ids = tuple(str(item) for item in known_node_ids)

        def build(
            *,
            action_type: str,
            payload: ActionChangePayload | None,
            diagnostics: Sequence[str],
            used_llm: bool,
            confident: bool,
        ) -> InterpretedAction:
            return InterpretedAction(
                action=_build_action(
                    session_id=session_id,
                    action_type=action_type,
                    payload=payload,
                    guide_id=guide_id,
                    expected_guide_version=expected_guide_version,
                    idempotency_key=idempotency_key,
                    raw_text=message or None,
                ),
                used_llm=used_llm,
                confident=confident,
                diagnostics=tuple(diagnostics),
            )

        if not message:
            fallback_action = self.fallback.interpret(
                session_id=session_id,
                text="",
                known_node_ids=node_ids,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                reference_date=reference_date,
            )
            return InterpretedAction(
                action=fallback_action,
                used_llm=False,
                confident=False,
                diagnostics=("本轮输入为空，无法识别修改意图",),
            )

        if not self.provider.is_available:
            fallback_action = self.fallback.interpret(
                session_id=session_id,
                text=message,
                known_node_ids=node_ids,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                reference_date=reference_date,
            )
            return InterpretedAction(
                action=fallback_action,
                used_llm=False,
                confident=False,
                diagnostics=(f"LLM 未配置（{self.provider.name}），已降级为关键词识别",),
            )

        try:
            payload = self.provider.complete_json(
                system=build_action_system_prompt(known_node_ids=node_ids),
                user=build_action_user_prompt(message),
            )
        except Exception as exc:  # noqa: BLE001
            # 同 B2/B4：通道失败一律降级到关键词识别，不让用户请求崩掉
            fallback_action = self.fallback.interpret(
                session_id=session_id,
                text=message,
                known_node_ids=node_ids,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                reference_date=reference_date,
            )
            return InterpretedAction(
                action=fallback_action,
                used_llm=False,
                confident=False,
                diagnostics=(
                    f"LLM 调用失败（{type(exc).__name__}: {exc}），已降级为关键词识别",
                ),
            )

        diagnostics: list[str] = []
        action_type = normalize_choice(payload.get("action_type"), ACTION_TYPES) or "MODIFY_GUIDE"

        if action_type in _PAYLOADLESS_ACTIONS:
            if payload.get("payload"):
                diagnostics.append(f"{action_type} 不需要 payload，模型给出的内容已忽略")
            return build(
                action_type=action_type,
                payload=None,
                diagnostics=diagnostics,
                used_llm=True,
                confident=True,
            )

        payload_field = payload.get("payload")
        if not isinstance(payload_field, Mapping):
            diagnostics.append("模型没有给出 payload，已降级为关键词识别")
            fallback_action = self.fallback.interpret(
                session_id=session_id,
                text=message,
                known_node_ids=node_ids,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                reference_date=reference_date,
            )
            return InterpretedAction(
                action=fallback_action,
                used_llm=False,
                confident=False,
                diagnostics=tuple(diagnostics),
            )

        change_type = normalize_choice(payload_field.get("change_type"), CHANGE_TYPES)
        if not change_type:
            given = payload_field.get("change_type")
            diagnostics.append(f"模型给出的 change_type {given!r} 不在契约取值集合内")
            return build(
                action_type="MODIFY_GUIDE",
                payload=ActionChangePayload(
                    change_type="REPLACE_NODE",
                    scope_hint=_derive_scope(message, ()),
                    date=_extract_date(message, reference_date),
                    target_node_ids=[],
                ),
                diagnostics=diagnostics,
                used_llm=True,
                confident=False,
            )

        target_ids, id_diagnostics = _filter_node_ids(
            payload_field.get("target_node_ids"), node_ids
        )
        diagnostics.extend(id_diagnostics)

        scope_hint = normalize_choice(payload_field.get("scope_hint"), SCOPE_HINTS)
        if not scope_hint:
            scope_hint = _derive_scope(message, target_ids)

        change_date = _coerce_date(payload_field.get("date")) or _extract_date(message, reference_date)

        try:
            payload_model = ActionChangePayload(
                change_type=change_type,  # type: ignore[arg-type]
                scope_hint=scope_hint,  # type: ignore[arg-type]
                date=change_date,
                target_node_ids=target_ids,
            )
        except ValidationError as exc:
            diagnostics.append(f"模型给出的 payload 不合法（{exc.error_count()} 处），已降级")
            fallback_action = self.fallback.interpret(
                session_id=session_id,
                text=message,
                known_node_ids=node_ids,
                guide_id=guide_id,
                expected_guide_version=expected_guide_version,
                idempotency_key=idempotency_key,
                reference_date=reference_date,
            )
            return InterpretedAction(
                action=fallback_action,
                used_llm=False,
                confident=False,
                diagnostics=tuple(diagnostics),
            )

        if change_type in ("REMOVE_NODE", "REPLACE_NODE", "ADD_FIXED_NODE") and not target_ids:
            diagnostics.append("模型没有给出具体节点 ID，需向用户确认要改哪一天/哪个安排")

        return build(
            action_type="MODIFY_GUIDE",
            payload=payload_model,
            diagnostics=diagnostics,
            used_llm=True,
            confident=bool(target_ids) or change_type not in ("REMOVE_NODE", "REPLACE_NODE", "ADD_FIXED_NODE"),
        )


# --- 工具 -------------------------------------------------------------------


def _build_action(
    *,
    session_id: str,
    action_type: str,
    payload: ActionChangePayload | None,
    guide_id: str | None,
    expected_guide_version: int | None,
    idempotency_key: str | None,
    raw_text: str | None,
) -> UserAction:
    return UserAction(
        action_id=f"act_{uuid.uuid4().hex[:12]}",
        idempotency_key=idempotency_key,
        action_type=action_type,  # type: ignore[arg-type]
        session_id=session_id,
        guide_id=guide_id,
        expected_guide_version=expected_guide_version,
        raw_text=raw_text,
        payload=payload,
    )


def _filter_node_ids(
    raw: Any, known_node_ids: Sequence[str]
) -> tuple[list[str], list[str]]:
    """只接受已知节点 ID。越界 ID 丢弃并记录 —— 下游重规划要靠它定位。"""

    diagnostics: list[str] = []
    known = set(known_node_ids)
    if raw is None:
        return [], diagnostics
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    accepted: list[str] = []
    for item in items:
        identifier = str(item or "").strip()
        if not identifier:
            continue
        if known and identifier not in known:
            diagnostics.append(f"模型给出的节点 {identifier} 不在已知节点清单内，已丢弃")
            continue
        if not known:
            diagnostics.append(f"调用方未提供已知节点清单，已丢弃模型给出的节点 {identifier}")
            continue
        if identifier not in accepted:
            accepted.append(identifier)
    return accepted, diagnostics


def _derive_scope(message: str, target_node_ids: Sequence[str]) -> str:
    if target_node_ids:
        return "NODE"
    if any(word in message for word in ("整个行程", "全部", "整体", "所有安排")):
        return "WHOLE_GUIDE"
    if any(word in message for word in ("住宿", "酒店", "住的地方", "住处")):
        return "STAY_SEGMENT"
    if any(word in message for word in ("这一天", "当天", "这天", "那天", "第几天")):
        return "DAY"
    return "WHOLE_GUIDE"


def _extract_date(message: str, reference: date | None = None) -> date | None:
    """从文本里抓一个明确日期；只有相对天数（「晚一天」）时返回 None。

    没有年份的月日（"10月3号"）用 `reference`（默认今天）补年份，
    已过去的日期按明年理解——与 B2 需求提取的日期口径保持一致。
    """

    match = _DATE_RE.search(message)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    anchor = reference or date.today()
    short = _SHORT_DATE_RE.search(message)
    if short:
        try:
            candidate = date(anchor.year, int(short.group(1)), int(short.group(2)))
        except ValueError:
            return None
        if candidate < anchor - timedelta(days=1):
            try:
                candidate = candidate.replace(year=anchor.year + 1)
            except ValueError:
                return None
        return candidate
    return None


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


__all__ = [
    "ACTION_TYPES",
    "CHANGE_TYPES",
    "SCOPE_HINTS",
    "InterpretedAction",
    "LLMUserActionInterpreter",
    "RuleBasedUserActionInterpreter",
    "UserActionInterpreter",
]
