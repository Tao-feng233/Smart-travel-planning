"""B2：把用户自然语言提取成 `TripProfileDraft`（LLM 正式实现）。

替换点：`app.services.request_parser.TripProfileParser` 协议（同一个 `parse` 签名）。
C 线的 `StubTripProfileParser` **原样保留**，作为本实现失败时的明确降级出口 ——
这样「模型连不上」不会让整个追问回路瘫掉，只是退回规则式提取。

红线（`AGENTS.md`）：

* 只填用户**说过**的信息，没说的留空，交给 B3 追问；
* 不产生任何旅游事实（开放时间/价格/路线/住宿/餐饮/天气）；
* 用户随口提的偏好只能是 SOFT 约束，不得升级成 FIXED（见 `guards.clean_constraints`）；
* 目的地 ID 只能取自 `known_destinations`，越界 ID 直接丢弃并记录；
* `must_visit_resource_ids` 只能来自数据层，**一律不采信模型输出**。

与 C 线 STUB 的一处有意差异：STUB 允许「没写年份且日期已过就按明年理解」，
本实现**不做年份推断**，遇到已经过去的日期直接丢弃并让 B3 重新追问 ——
模型已经给出了完整年份，再替它改年份等于伪造用户意图。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from app.schemas import DestinationRequest, TripProfileDraft
from app.services.request_parser import TripProfileParser, StubTripProfileParser

from .guards import (
    clean_constraints,
    normalize_choice,
    normalize_hhmm,
    normalize_money,
    normalize_string_list,
    normalize_tag_list,
)
from .prompts import (
    build_profile_repair_prompt,
    build_profile_system_prompt,
    build_profile_user_prompt,
)
from .provider import LLMProvider

logger = logging.getLogger(__name__)


def _safe(exc: BaseException) -> str:
    """异常信息进日志/诊断前的安全截断（不含任何凭据）。"""

    return f"{type(exc).__name__}: {exc}"[:200]


_PACE_VALUES = ("RELAXED", "BALANCED", "INTENSE")
_FLEXIBILITY_VALUES = ("FIXED", "NEGOTIABLE")
_PRIORITY_VALUES = ("LOW", "MEDIUM", "HIGH")

#: 需要「模型优先、规则补空」的标量字段
_ASSIST_SCALAR_FIELDS = (
    "departure_city",
    "start_date",
    "end_date",
    "traveler_count",
    "budget",
)
#: 需要「模型优先、规则补空」的列表字段
_ASSIST_LIST_FIELDS = ("interests", "avoidances")

#: `duration_days` 由 `finalize_trip_profile` 从起止日期推导，模型填了也不用
_DERIVED_FIELDS = ("duration_days",)


@dataclass(frozen=True)
class ParseOutcome:
    """一次解析的完整结果（协议只要求 `draft`，诊断信息供测试与联调使用）。"""

    draft: TripProfileDraft
    used_llm: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeResult:
    """合并结果。

    `blocked_fields` 记录**被校验收掉**的字段（例如已经过去的日期、
    早于出发日期的返回日期）。规则式兜底不得再去填它们 ——
    否则「校验收掉」会被「规则补回」抵消，红线就形同虚设。
    """

    payload: dict[str, Any]
    diagnostics: list[str]
    blocked_fields: frozenset[str]


@dataclass
class LLMTripProfileParser:
    """LLM 版需求提取器。

    `provider` 不可用、调用失败、或输出连续不合法时，自动降级到规则式解析器，
    并把原因写进 `diagnostics` —— 降级必须**可见**，不能静默。
    """

    provider: LLMProvider
    fallback: TripProfileParser = field(default_factory=StubTripProfileParser)
    max_repair_attempts: int = 1
    #: 用规则式解析器补模型漏掉的明显字段（预算数字、人名数量等）；模型结果优先
    use_rule_assist: bool = True

    # --- 协议入口 -----------------------------------------------------------

    def parse(
        self,
        *,
        session_id: str,
        text: str,
        previous: TripProfileDraft | None,
        reference_date: date,
        known_destinations: Mapping[str, str] | None = None,
    ) -> TripProfileDraft:
        return self.parse_with_diagnostics(
            session_id=session_id,
            text=text,
            previous=previous,
            reference_date=reference_date,
            known_destinations=known_destinations,
        ).draft

    # --- 带诊断的入口 -------------------------------------------------------

    def parse_with_diagnostics(
        self,
        *,
        session_id: str,
        text: str,
        previous: TripProfileDraft | None,
        reference_date: date,
        known_destinations: Mapping[str, str] | None = None,
    ) -> ParseOutcome:
        known = dict(known_destinations or {})
        base = _copy_or_new(previous, session_id)
        message = (text or "").strip()

        if not message:
            return ParseOutcome(
                draft=base,
                used_llm=False,
                diagnostics=("本轮输入为空，沿用已有画像",),
            )

        if not self.provider.is_available:
            return self._degrade(
                session_id=session_id,
                text=message,
                previous=previous,
                reference_date=reference_date,
                known=known,
                reason=f"LLM 未配置（{self.provider.name}），已降级为规则式解析",
            )

        system = build_profile_system_prompt(
            reference_date=reference_date,
            known_destinations=known,
            previous=previous,
        )
        user_prompt = build_profile_user_prompt(message)
        diagnostics: list[str] = []

        for attempt in range(self.max_repair_attempts + 1):
            try:
                payload = self.provider.complete_json(system=system, user=user_prompt)
            except Exception as exc:  # noqa: BLE001
                # 有意捕获所有异常：模型通道的任何失败（未配置、超时、网关 5xx、
                # SDK 自身报错）都不应该让用户请求崩掉，而是走明确降级。
                # 只包住这一次调用，后面的合并/校验代码不受影响，不会掩盖自身 bug。
                return self._degrade(
                    session_id=session_id,
                    text=message,
                    previous=previous,
                    reference_date=reference_date,
                    known=known,
                    reason=f"LLM 调用失败（{_safe(exc)}），已降级为规则式解析",
                )

            merge_result = merge_profile_payload(
                base=base,
                payload=payload,
                known=known,
                reference_date=reference_date,
            )
            merged = merge_result.payload
            diagnostics.extend(merge_result.diagnostics)

            if self.use_rule_assist:
                merged, assist_diagnostics = self._apply_rule_assist(
                    merged=merged,
                    text=message,
                    reference_date=reference_date,
                    known=known,
                    blocked=merge_result.blocked_fields,
                )
                diagnostics.extend(assist_diagnostics)

            try:
                draft = TripProfileDraft.model_validate(merged)
            except ValidationError as exc:
                summary = _summarize_validation_error(exc)
                diagnostics.append(
                    f"第 {attempt + 1} 次模型输出未通过契约校验（{summary}），已要求修正"
                )
                if attempt < self.max_repair_attempts:
                    user_prompt = build_profile_repair_prompt(
                        message, error=summary, payload=merged
                    )
                    continue
                return self._degrade(
                    session_id=session_id,
                    text=message,
                    previous=previous,
                    reference_date=reference_date,
                    known=known,
                    reason="LLM 输出连续不合法，已降级为规则式解析",
                    extra=tuple(diagnostics),
                )

            return ParseOutcome(
                draft=_finalize_draft(draft, session_id),
                used_llm=True,
                diagnostics=tuple(diagnostics),
            )

        # 正常流程不会走到这里，保留兜底以免将来改循环时漏出口
        return self._degrade(  # pragma: no cover
            session_id=session_id,
            text=message,
            previous=previous,
            reference_date=reference_date,
            known=known,
            reason="LLM 输出不可用，已降级为规则式解析",
            extra=tuple(diagnostics),
        )

    # --- 内部 ---------------------------------------------------------------

    def _apply_rule_assist(
        self,
        *,
        merged: dict[str, Any],
        text: str,
        reference_date: date,
        known: Mapping[str, str],
        blocked: frozenset[str] = frozenset(),
    ) -> tuple[dict[str, Any], list[str]]:
        """用规则式解析器补模型漏掉的字段（模型已有的值不动，被校验收掉的不补）。"""

        rule_draft = self.fallback.parse(
            session_id=str(merged.get("session_id") or "session"),
            text=text,
            previous=None,
            reference_date=reference_date,
            known_destinations=known,
        )
        diagnostics: list[str] = []
        result = dict(merged)

        for name in _ASSIST_SCALAR_FIELDS:
            if name in blocked:
                # 该字段是本轮被红线校验明确收掉的，不能靠规则再填回来
                continue
            if not _is_empty(result.get(name)):
                continue
            candidate = getattr(rule_draft, name, None)
            if _is_empty(candidate):
                continue
            result[name] = candidate
            diagnostics.append(f"模型未提取到 {name}，已由规则式解析补齐")

        for name in _ASSIST_LIST_FIELDS:
            candidate = getattr(rule_draft, name, None) or []
            if not candidate:
                continue
            existing = result.get(name) or []
            merged_list = list(existing)
            for item in candidate:
                if item not in merged_list:
                    merged_list.append(item)
            if len(merged_list) != len(existing):
                result[name] = merged_list
                diagnostics.append(f"规则式解析为 {name} 补充了标签")

        return result, diagnostics

    def _degrade(
        self,
        *,
        session_id: str,
        text: str,
        previous: TripProfileDraft | None,
        reference_date: date,
        known: Mapping[str, str],
        reason: str,
        extra: Sequence[str] = (),
    ) -> ParseOutcome:
        draft = self.fallback.parse(
            session_id=session_id,
            text=text,
            previous=previous,
            reference_date=reference_date,
            known_destinations=known,
        )
        logger.info("B2 降级为规则式解析：%s", reason)
        return ParseOutcome(
            draft=draft,
            used_llm=False,
            diagnostics=(reason, *extra),
        )


# --- 合并 -------------------------------------------------------------------


def merge_profile_payload(
    *,
    base: TripProfileDraft,
    payload: Mapping[str, Any],
    known: Mapping[str, str],
    reference_date: date,
) -> MergeResult:
    """把模型输出合并进已有 Draft，并做全部机械红线校验。

    合并策略：**模型这一轮说过的覆盖，没说的保留原有**。
    用户补充信息时会推翻之前的说法，所以覆盖是对的；
    但「这一轮没提到」不等于「用户收回了」，所以不能清空。
    """

    diagnostics: list[str] = []
    blocked: set[str] = set()
    merged: dict[str, Any] = base.model_dump()
    for name in _DERIVED_FIELDS:
        merged.pop(name, None)

    if payload.get("session_id") not in (None, base.session_id):
        diagnostics.append("模型试图改写 session_id，已忽略")

    # 城市：字符串即可，不做白名单（出发地不要求是知识库里的目的地）
    city = _clean_text(payload.get("departure_city"))
    if city:
        merged["departure_city"] = city

    for name in ("start_date", "end_date"):
        if name not in payload:
            continue
        raw_value = payload.get(name)
        value, note = _coerce_upcoming_date(raw_value, reference_date)
        if note:
            diagnostics.append(note)
        if value is not None:
            merged[name] = value
        elif raw_value is not None:
            # 模型给了但不可用：清掉、记为「已收掉」，交回 B3 追问
            merged[name] = None
            blocked.add(name)

    _guard_date_order(merged, base=base, diagnostics=diagnostics, blocked=blocked)

    travelers = _positive_int(payload.get("traveler_count"))
    if travelers is not None:
        merged["traveler_count"] = travelers

    composition = _normalize_composition(payload.get("traveler_composition"))
    if composition is not None:
        if travelers is not None and sum(composition.values()) != travelers:
            diagnostics.append(
                "模型给出的人数构成与总人数不一致，已丢弃构成并等用户确认"
            )
            merged["traveler_composition"] = None
        else:
            merged["traveler_composition"] = composition

    money = normalize_money(payload.get("budget"))
    if money is not None:
        merged["budget"] = money

    flexibility = normalize_choice(payload.get("budget_flexibility"), _FLEXIBILITY_VALUES)
    if flexibility:
        merged["budget_flexibility"] = flexibility

    pace = normalize_choice(payload.get("pace"), _PACE_VALUES)
    if pace:
        merged["pace"] = pace

    for name in (
        "interests",
        "avoidances",
        "mobility_constraints",
        "dietary_constraints",
        "lodging_preferences",
        "transport_preferences",
    ):
        # 兴趣/避讳归一到规范词表，避免与规则式兜底的标签同义重复
        additions = (
            normalize_tag_list(payload.get(name), field=name)
            if name in ("interests", "avoidances")
            else normalize_string_list(payload.get(name))
        )
        if additions:
            existing = list(merged.get(name) or [])
            for item in additions:
                if item not in existing:
                    existing.append(item)
            merged[name] = existing

    for name in ("earliest_day_start", "latest_day_end"):
        hhmm = normalize_hhmm(payload.get(name))
        if hhmm:
            merged[name] = hhmm

    # 资源 ID 只能来自数据层，模型无从得知 → 一律不采信
    if payload.get("must_visit_resource_ids"):
        diagnostics.append(
            "模型输出了 must_visit_resource_ids，但资源 ID 只能来自数据层，已忽略"
        )

    requests, request_diagnostics = _accept_destination_requests(
        payload.get("destination_requests"),
        base=base,
        known=known,
    )
    diagnostics.extend(request_diagnostics)
    merged["destination_requests"] = requests
    # 目的地个数决定 destination_mode，不采信模型的声明
    merged["destination_mode"] = _derive_destination_mode(requests)

    constraints, constraint_diagnostics = clean_constraints(
        payload.get("constraints"),
        base=[item.model_dump() for item in base.constraints],
    )
    diagnostics.extend(constraint_diagnostics)
    merged["constraints"] = constraints

    return MergeResult(
        payload=merged, diagnostics=diagnostics, blocked_fields=frozenset(blocked)
    )


def _copy_or_new(previous: TripProfileDraft | None, session_id: str) -> TripProfileDraft:
    if previous is None:
        return TripProfileDraft(session_id=session_id)
    copied = previous.model_copy(deep=True)
    copied.session_id = session_id
    return copied


def _finalize_draft(draft: TripProfileDraft, session_id: str) -> TripProfileDraft:
    """统一收口：系统字段由系统说了算。"""

    draft.session_id = session_id
    draft.profile_version = 0
    draft.duration_days = None
    draft.missing_fields = draft.compute_missing_fields()
    return draft


def _accept_destination_requests(
    raw: Any,
    *,
    base: TripProfileDraft,
    known: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """只接受知识库清单内的目的地 ID；名称一律以清单为准。

    模型很容易把用户说的城市名直接当 `destination_id`（例如 "成都"），
    或者编一个看起来合理的 ID。这一层是**硬闸门**：
    不在清单里的直接丢弃并记录，绝不带进下游。
    """

    diagnostics: list[str] = []
    allowed = set(known.values())
    name_by_id = {identifier: name for name, identifier in known.items()}

    accepted: dict[str, dict[str, Any]] = {
        item.destination_id: item.model_dump() for item in base.destination_requests
    }

    items = raw if isinstance(raw, (list, tuple)) else ([raw] if raw else [])
    for item in items:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("destination_id") or "").strip()
        if identifier not in allowed:
            diagnostics.append(
                f"模型给出的目的地 {identifier or '<空>'} 不在知识库清单内，已丢弃"
            )
            continue
        entry = accepted.get(identifier, {})
        entry["destination_id"] = identifier
        # 名称一律用清单里的，防止模型自行编造中文名
        entry["name"] = name_by_id.get(identifier) or entry.get("name") or identifier
        for name in ("desired_days", "min_days", "max_days", "user_reason"):
            value = item.get(name)
            if value not in (None, ""):
                entry[name] = value
        priority = normalize_choice(item.get("priority"), _PRIORITY_VALUES)
        entry["priority"] = priority or entry.get("priority") or "MEDIUM"
        fixed = item.get("fixed")
        entry["fixed"] = bool(fixed) if isinstance(fixed, bool) else entry.get("fixed", True)
        accepted[identifier] = entry

    return list(accepted.values()), diagnostics


def _derive_destination_mode(requests: Sequence[Mapping[str, Any]]) -> str:
    if len(requests) > 1:
        return "MULTIPLE"
    if len(requests) == 1:
        return "SINGLE"
    return "UNKNOWN"


def _guard_date_order(
    merged: dict[str, Any],
    *,
    base: TripProfileDraft,
    diagnostics: list[str],
    blocked: set[str],
) -> None:
    start = merged.get("start_date")
    end = merged.get("end_date")
    if not isinstance(start, date) or not isinstance(end, date):
        return
    if end < start:
        diagnostics.append(
            f"模型给出的返回日期（{end.isoformat()}）早于出发日期"
            f"（{start.isoformat()}），已丢弃返回日期并重新追问"
        )
        merged["end_date"] = base.end_date if _is_after(base.end_date, start) else None
        blocked.add("end_date")


def _coerce_upcoming_date(
    value: Any, reference_date: date
) -> tuple[date | None, str | None]:
    """把模型给的日期转成 `date`，并拒绝已经过去的日期。"""

    if value is None or value == "":
        return None, None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = date.fromisoformat(text[:10])
        except ValueError:
            return None, f"模型给出的日期 {text!r} 无法解析，已丢弃"
    if parsed < reference_date:
        return None, (
            f"模型给出的日期 {parsed.isoformat()} 早于今天（{reference_date.isoformat()}），"
            "已丢弃并重新追问"
        )
    return parsed, None


def _normalize_composition(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    parts = {
        name: _non_negative_int(value.get(name)) or 0
        for name in ("adults", "children", "seniors")
    }
    if sum(parts.values()) <= 0:
        return None
    return parts


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _is_after(value: Any, threshold: date) -> bool:
    return isinstance(value, date) and value >= threshold


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _non_negative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _summarize_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors()[:5]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg')}")
    return "；".join(parts) or "结构不合法"


__all__ = ["LLMTripProfileParser", "MergeResult", "ParseOutcome", "merge_profile_payload"]
