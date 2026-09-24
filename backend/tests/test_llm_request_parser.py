"""B2：LLM 需求提取（`LLMTripProfileParser`）测试。

覆盖三类场景（`AGENTS.md` 要求每个功能至少含正常、失败、数据不足）：
正常提取 / 模型不可用降级 / 输出越界与不合规时的拦截。
"""

from __future__ import annotations

from datetime import date

from b_line_fakes import FakeLLMProvider
from app.schemas import Money, TripProfileDraft, finalize_trip_profile
from app.llm.request_parser import LLMTripProfileParser

REFERENCE = date(2026, 9, 24)
KNOWN = {"成都": "dest_chengdu", "乐山": "dest_leshan"}
SESSION = "sess_b2"

_TEXT = "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，轻松一点，就去成都"

_COMPLETE = {
    "departure_city": "上海",
    "start_date": "2026-10-02",
    "end_date": "2026-10-06",
    "traveler_count": 2,
    "budget": {"amount": 5000, "currency": "CNY"},
    "pace": "RELAXED",
    "interests": ["FOOD", "CULTURE"],
    "destination_requests": [
        {"destination_id": "dest_chengdu", "fixed": True, "priority": "HIGH"}
    ],
}


def _outcome(payloads, *, text=_TEXT, previous=None, available=True, error=None, **kwargs):
    parser = LLMTripProfileParser(
        provider=FakeLLMProvider(*payloads, available=available, error=error), **kwargs
    )
    return parser.parse_with_diagnostics(
        session_id=SESSION,
        text=text,
        previous=previous,
        reference_date=REFERENCE,
        known_destinations=KNOWN,
    )


# --- 正常场景 ---------------------------------------------------------------


def test_llm_extracts_a_complete_profile() -> None:
    outcome = _outcome([_COMPLETE])
    draft = outcome.draft

    assert outcome.used_llm is True
    assert draft.missing_fields == []
    assert draft.session_id == SESSION

    profile = finalize_trip_profile(draft)
    assert profile.departure_city == "上海"
    assert profile.duration_days == 5  # 含首尾
    assert profile.traveler_count == 2
    assert profile.budget.amount == 5000
    assert profile.pace == "RELAXED"
    assert profile.destination_mode == "SINGLE"
    assert profile.destination_requests[0].name == "成都"


def test_destination_name_always_comes_from_the_catalog() -> None:
    """模型自己编的中文名不能用，名称一律以知识库清单为准。"""

    payload = dict(_COMPLETE)
    payload["destination_requests"] = [
        {"destination_id": "dest_chengdu", "name": "成都市天府新区", "priority": "HIGH"}
    ]
    draft = _outcome([payload]).draft
    assert draft.destination_requests[0].name == "成都"


def test_destination_mode_is_derived_from_requests() -> None:
    payload = dict(_COMPLETE)
    payload["destination_requests"] = [
        {"destination_id": "dest_chengdu"},
        {"destination_id": "dest_leshan"},
    ]
    payload["destination_mode"] = "SINGLE"  # 模型声明与事实不符
    draft = _outcome([payload]).draft
    assert draft.destination_mode == "MULTIPLE"


def test_duration_days_is_left_to_finalize() -> None:
    payload = dict(_COMPLETE, duration_days=99)
    draft = _outcome([payload]).draft
    assert draft.duration_days is None

    profile = finalize_trip_profile(draft)
    assert profile.duration_days == 5


def test_previous_values_survive_a_silent_turn() -> None:
    previous = TripProfileDraft(
        session_id=SESSION,
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        traveler_count=2,
        budget=Money(amount=5000),
        pace="RELAXED",
    )
    outcome = _outcome([{}], text="嗯，就这样", previous=previous)
    draft = outcome.draft

    assert draft.departure_city == "上海"
    assert draft.start_date == date(2026, 10, 2)
    assert draft.budget is not None and draft.budget.amount == 5000
    assert draft.missing_fields == []


def test_model_can_override_a_previous_value() -> None:
    previous = TripProfileDraft(
        session_id=SESSION, traveler_count=2, pace="RELAXED"
    )
    payload = {"traveler_count": 4, "pace": "INTENSE"}
    draft = _outcome([payload], text="改成四个人，安排紧凑一点", previous=previous).draft
    assert draft.traveler_count == 4
    assert draft.pace == "INTENSE"


def test_rule_assist_fills_a_field_the_model_missed() -> None:
    """模型漏了预算，但文本里有明确数字：规则式解析补上，并如实记录。"""

    payload = dict(_COMPLETE)
    payload["budget"] = None
    outcome = _outcome([payload], text="预算8000元，其他按刚才说的")
    assert outcome.draft.budget is not None
    assert outcome.draft.budget.amount == 8000
    assert any("budget" in note and "规则式解析补齐" in note for note in outcome.diagnostics)


def test_rule_assist_cannot_resurrect_a_rejected_field() -> None:
    """被红线校验收掉的字段，规则式兜底不得再填回来。

    否则「模型给出已过去的日期 → 系统收掉 → 规则又补上」会让校验收了个寂寞。
    """

    payload = dict(_COMPLETE, start_date="2026-01-01", end_date="2026-01-05")
    outcome = _outcome([payload], text="从上海出发，10月2号到10月6号，2个人")
    assert outcome.draft.start_date is None
    assert outcome.draft.end_date is None


# --- 数据不足 / 降级场景 ----------------------------------------------------


def test_unavailable_provider_degrades_to_rules() -> None:
    outcome = _outcome([], text=_TEXT, available=False)
    assert outcome.used_llm is False
    assert outcome.draft.departure_city == "上海"  # 规则式解析仍然抽到了出发点
    assert any("降级为规则式解析" in note for note in outcome.diagnostics)


def test_provider_failure_degrades_to_rules() -> None:
    outcome = _outcome([], text=_TEXT, error=RuntimeError("连接被重置"))
    assert outcome.used_llm is False
    assert any("降级为规则式解析" in note for note in outcome.diagnostics)


def test_empty_input_never_calls_the_model() -> None:
    parser = LLMTripProfileParser(provider=FakeLLMProvider(_COMPLETE))
    previous = TripProfileDraft(session_id=SESSION, traveler_count=2)
    outcome = parser.parse_with_diagnostics(
        session_id=SESSION,
        text="   ",
        previous=previous,
        reference_date=REFERENCE,
        known_destinations=KNOWN,
    )
    assert outcome.used_llm is False
    assert outcome.draft.traveler_count == 2
    assert parser.provider.calls == []  # type: ignore[attr-defined]


def test_two_invalid_outputs_degrade_to_rules() -> None:
    bad = {
        "destination_requests": [
            {"destination_id": "dest_chengdu", "desired_days": {"不是": "数字"}}
        ]
    }
    parser = LLMTripProfileParser(provider=FakeLLMProvider(bad, bad))
    outcome = parser.parse_with_diagnostics(
        session_id=SESSION,
        text=_TEXT,
        previous=None,
        reference_date=REFERENCE,
        known_destinations=KNOWN,
    )
    assert outcome.used_llm is False
    assert any("未通过契约校验" in note for note in outcome.diagnostics)
    assert any("降级为规则式解析" in note for note in outcome.diagnostics)


def test_invalid_output_is_repaired_on_the_second_try() -> None:
    bad = {
        "destination_requests": [
            {"destination_id": "dest_chengdu", "desired_days": {"不是": "数字"}}
        ]
    }
    parser = LLMTripProfileParser(provider=FakeLLMProvider(bad, _COMPLETE))
    outcome = parser.parse_with_diagnostics(
        session_id=SESSION,
        text=_TEXT,
        previous=None,
        reference_date=REFERENCE,
        known_destinations=KNOWN,
    )
    assert outcome.used_llm is True
    assert outcome.draft.missing_fields == []
    assert any("要求修正" in note for note in outcome.diagnostics)


# --- 红线拦截 ---------------------------------------------------------------


def test_out_of_catalog_destination_is_dropped() -> None:
    payload = dict(_COMPLETE)
    payload["destination_requests"] = [
        {"destination_id": "dest_beijing", "fixed": True, "priority": "HIGH"}
    ]
    outcome = _outcome([payload], text="想去北京玩")
    assert outcome.draft.destination_requests == []
    assert outcome.draft.destination_mode == "UNKNOWN"
    assert any("不在知识库清单内" in note for note in outcome.diagnostics)


def test_past_date_is_dropped_and_asked_again() -> None:
    payload = dict(_COMPLETE, start_date="2026-01-01", end_date="2026-01-05")
    outcome = _outcome([payload])
    assert outcome.draft.start_date is None
    assert "start_date" in outcome.draft.missing_fields
    assert any("早于今天" in note for note in outcome.diagnostics)


def test_reversed_date_range_drops_the_end_date() -> None:
    payload = dict(_COMPLETE, start_date="2026-10-06", end_date="2026-10-02")
    outcome = _outcome([payload])
    assert outcome.draft.start_date == date(2026, 10, 6)
    assert outcome.draft.end_date is None
    assert any("早于出发日期" in note for note in outcome.diagnostics)


def test_model_cannot_declare_a_fixed_constraint() -> None:
    payload = dict(
        _COMPLETE,
        constraints=[
            {
                "constraint_id": "c_budget",
                "kind": "FIXED",
                "field": "budget",
                "operator": "LTE",
                "value": 5000,
            }
        ],
    )
    outcome = _outcome([payload])
    assert outcome.draft.constraints[0].kind == "SOFT"
    assert any("已按 SOFT 处理" in note for note in outcome.diagnostics)


def test_must_visit_resource_ids_are_never_taken_from_the_model() -> None:
    payload = dict(_COMPLETE, must_visit_resource_ids=["poi_9999"])
    outcome = _outcome([payload])
    assert outcome.draft.must_visit_resource_ids == []
    assert any("只能来自数据层" in note for note in outcome.diagnostics)


def test_illegal_constraint_operator_is_dropped() -> None:
    payload = dict(
        _COMPLETE,
        constraints=[
            {
                "constraint_id": "c_x",
                "kind": "SOFT",
                "field": "pace",
                "operator": "APPROXIMATELY",
                "value": "RELAXED",
            }
        ],
    )
    outcome = _outcome([payload])
    assert outcome.draft.constraints == []
    assert any("算子" in note for note in outcome.diagnostics)


# --- Money 形状归一化 -------------------------------------------------------


def test_money_with_only_a_lower_bound_becomes_exact() -> None:
    payload = dict(_COMPLETE, budget={"min_amount": 5000})
    draft = _outcome([payload]).draft
    assert draft.budget is not None
    assert draft.budget.amount == 5000
    assert draft.budget.min_amount is None


def test_money_with_only_an_upper_bound_becomes_exact() -> None:
    payload = dict(_COMPLETE, budget={"max_amount": 6000})
    draft = _outcome([payload]).draft
    assert draft.budget is not None
    assert draft.budget.amount == 6000


def test_reversed_money_range_is_ordered() -> None:
    payload = dict(_COMPLETE, budget={"min_amount": 9000, "max_amount": 5000})
    draft = _outcome([payload]).draft
    assert draft.budget is not None
    assert draft.budget.min_amount == 5000
    assert draft.budget.max_amount == 9000


# --- 标签归一化（回归）-----------------------------------------------------


def test_chinese_interest_words_are_normalized_to_canonical_tags() -> None:
    """模型返回中文兴趣词时会与规则式兜底的英文标签同义重复。

    端到端联调实测出现过 `['美食', 'FOOD']`：模型写中文、规则兜底补英文，
    下游按标签匹配资源会漏。归一后应只剩规范标签。
    """

    payload = dict(_COMPLETE, interests=["美食", "人文"])
    draft = _outcome([payload]).draft
    assert "FOOD" in draft.interests
    assert "CULTURE" in draft.interests
    assert "美食" not in draft.interests
    assert "人文" not in draft.interests
    # 同义重复必须消掉
    assert len(draft.interests) == len(set(draft.interests))


def test_unknown_interest_tag_is_kept_as_is() -> None:
    """词表外的兴趣不丢——契约里 interests 没有枚举约束，不能替用户删信息。"""

    payload = dict(_COMPLETE, interests=["摄影"])
    draft = _outcome([payload]).draft
    assert "摄影" in draft.interests


def test_avoidance_words_are_normalized_too() -> None:
    payload = dict(_COMPLETE, avoidances=["不想爬山"])
    draft = _outcome([payload]).draft
    assert "HIGH_INTENSITY_HIKING" in draft.avoidances
    assert "不想爬山" not in draft.avoidances
