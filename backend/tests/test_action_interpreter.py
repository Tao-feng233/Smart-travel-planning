"""B5：修改意图识别（`UserAction`）测试。

覆盖：删除 / 替换 / 减轻强度 / 换日期 / 预算 / 确认这几类意图，
以及「节点 ID 越界」「change_type 不在契约里」两种必须被拦住的输入。

后端还没有接收 `UserAction` 的路由（C7 未实现），所以本文件直接调用解析器。
"""

from __future__ import annotations

from datetime import date

from b_line_fakes import FakeLLMProvider
from app.schemas import ActionChangePayload, UserAction
from app.llm.action_interpreter import (
    CHANGE_TYPES,
    LLMUserActionInterpreter,
    RuleBasedUserActionInterpreter,
    SCOPE_HINTS,
)

SESSION = "sess_b5"
NODES = ("node_001", "node_002", "node_arrive")


def _rules(text: str) -> UserAction:
    return RuleBasedUserActionInterpreter().interpret(
        session_id=SESSION, text=text, known_node_ids=NODES
    )


def _llm(payloads, *, text, available=True, error=None, node_ids=NODES):
    interpreter = LLMUserActionInterpreter(
        provider=FakeLLMProvider(*payloads, available=available, error=error)
    )
    return interpreter.interpret_with_diagnostics(
        session_id=SESSION, text=text, known_node_ids=node_ids
    )


# --- 规则式兜底 -------------------------------------------------------------


def test_rule_based_detects_removal() -> None:
    action = _rules("把博物馆那一条去掉")
    assert action.action_type == "MODIFY_GUIDE"
    assert action.payload is not None
    assert action.payload.change_type == "REMOVE_NODE"


def test_rule_based_detects_lower_intensity() -> None:
    action = _rules("第二天太累了，轻松一点")
    assert action.payload is not None
    assert action.payload.change_type == "LOWER_INTENSITY"


def test_rule_based_detects_budget_change() -> None:
    action = _rules("预算太贵了，能不能省点")
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_BUDGET"


def test_rule_based_detects_confirmation_without_payload() -> None:
    action = _rules("就这个吧，确认")
    assert action.action_type == "CONFIRM_GUIDE"
    assert action.payload is None


def test_rule_based_detects_a_concrete_date() -> None:
    action = _rules("把出发日期改到2026-10-04")
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_DATE"
    assert action.payload.date == date(2026, 10, 4)


def test_rule_based_never_guesses_node_ids() -> None:
    action = _rules("把第二天那个安排换掉")
    assert action.payload is not None
    assert action.payload.target_node_ids == []


def test_rule_based_action_ids_are_unique_and_prefixed() -> None:
    first, second = _rules("去掉第一条"), _rules("去掉第一条")
    assert first.action_id.startswith("act_")
    assert first.action_id != second.action_id


# --- LLM 正常场景 -----------------------------------------------------------


def test_llm_returns_a_contract_action() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {
            "change_type": "REMOVE_NODE",
            "scope_hint": "NODE",
            "target_node_ids": ["node_002"],
        },
    }
    result = _llm([payload], text="把第二个安排去掉")
    action = result.action

    assert result.used_llm is True
    assert result.confident is True
    assert action.action_type == "MODIFY_GUIDE"
    assert action.payload is not None
    assert action.payload.change_type == "REMOVE_NODE"
    assert action.payload.scope_hint == "NODE"
    assert action.payload.target_node_ids == ["node_002"]
    assert action.raw_text == "把第二个安排去掉"
    # 系统字段由系统填
    assert action.session_id == SESSION
    assert action.action_id.startswith("act_")


def test_llm_payload_is_always_a_valid_contract_object() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {"change_type": "LOWER_INTENSITY", "scope_hint": "DAY"},
    }
    action = _llm([payload], text="第三天轻松一点").action
    assert isinstance(action.payload, ActionChangePayload)
    assert action.payload.change_type in CHANGE_TYPES
    assert action.payload.scope_hint in SCOPE_HINTS


def test_llm_can_change_the_date() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {
            "change_type": "CHANGE_DATE",
            "scope_hint": "WHOLE_GUIDE",
            "date": "2026-10-08",
        },
    }
    action = _llm([payload], text="整体推迟到10月8号").action
    assert action.payload is not None
    assert action.payload.date == date(2026, 10, 8)


def test_idempotency_key_is_passed_through() -> None:
    interpreter = LLMUserActionInterpreter(provider=FakeLLMProvider({"action_type": "CONFIRM_GUIDE"}))
    action = interpreter.interpret(
        session_id=SESSION,
        text="确认",
        known_node_ids=NODES,
        guide_id="guide_001",
        expected_guide_version=3,
        idempotency_key="idem_abc",
    )
    assert action.idempotency_key == "idem_abc"
    assert action.guide_id == "guide_001"
    assert action.expected_guide_version == 3


def test_confirmation_carries_no_payload() -> None:
    payload = {
        "action_type": "CONFIRM_GUIDE",
        "payload": {"change_type": "REMOVE_NODE", "scope_hint": "NODE"},
    }
    result = _llm([payload], text="就这样吧")
    assert result.action.payload is None
    assert any("不需要 payload" in note for note in result.diagnostics)


# --- 红线拦截 ---------------------------------------------------------------


def test_out_of_range_node_ids_are_dropped() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {
            "change_type": "REMOVE_NODE",
            "scope_hint": "NODE",
            "target_node_ids": ["node_001", "node_999"],
        },
    }
    result = _llm([payload], text="去掉第一个和第九个")
    assert result.action.payload is not None
    assert result.action.payload.target_node_ids == ["node_001"]
    assert any("不在已知节点清单内" in note for note in result.diagnostics)


def test_node_ids_are_all_dropped_when_no_catalog_is_supplied() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {
            "change_type": "REMOVE_NODE",
            "scope_hint": "NODE",
            "target_node_ids": ["node_001"],
        },
    }
    result = _llm([payload], text="去掉第一个", node_ids=())
    assert result.action.payload is not None
    assert result.action.payload.target_node_ids == []
    assert result.confident is False
    assert any("未提供已知节点清单" in note for note in result.diagnostics)


def test_unknown_change_type_falls_back_and_lowers_confidence() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {"change_type": "DELETE_EVERYTHING", "scope_hint": "WHOLE_GUIDE"},
    }
    result = _llm([payload], text="全部删掉重来")
    assert result.action.payload is not None
    assert result.action.payload.change_type == "REPLACE_NODE"
    assert result.confident is False
    assert any("不在契约取值集合内" in note for note in result.diagnostics)


def test_node_targeting_change_without_nodes_is_marked_unconfident() -> None:
    payload = {
        "action_type": "MODIFY_GUIDE",
        "payload": {"change_type": "REPLACE_NODE", "scope_hint": "DAY"},
    }
    result = _llm([payload], text="第二天换个别的")
    assert result.confident is False
    assert result.action.payload is not None
    assert result.action.payload.change_type == "REPLACE_NODE"


# --- 数据不足 / 降级场景 ----------------------------------------------------


def test_missing_payload_degrades_to_keywords() -> None:
    result = _llm([{"action_type": "MODIFY_GUIDE"}], text="预算加点")
    assert result.used_llm is False
    assert result.action.payload is not None
    assert result.action.payload.change_type == "CHANGE_BUDGET"


def test_unavailable_provider_degrades_to_keywords() -> None:
    result = _llm([], text="把第一个去掉", available=False)
    assert result.used_llm is False
    assert result.confident is False
    assert result.action.payload is not None
    assert result.action.payload.change_type == "REMOVE_NODE"


def test_provider_failure_degrades_to_keywords() -> None:
    result = _llm([], text="轻松一点", error=RuntimeError("超时"))
    assert result.used_llm is False
    assert result.action.payload is not None
    assert result.action.payload.change_type == "LOWER_INTENSITY"


def test_empty_input_is_not_interpreted_as_an_intent() -> None:
    result = _llm([{"action_type": "CONFIRM_GUIDE"}], text="   ")
    assert result.used_llm is False
    assert result.confident is False
    assert any("输入为空" in note for note in result.diagnostics)


# --- 日期补年份（回归）-------------------------------------------------------


def _llm_with_ref(payloads, *, text, reference):
    interpreter = LLMUserActionInterpreter(provider=FakeLLMProvider(*payloads))
    return interpreter.interpret_with_diagnostics(
        session_id=SESSION, text=text, known_node_ids=NODES, reference_date=reference
    )


def test_month_day_without_year_is_resolved_against_reference_date() -> None:
    """端到端联调发现「10月3号那天…」的日期完全没被填进 payload。

    用户改行程时几乎不会写年份，只认 `2026-10-03` 这种完整写法等于丢日期。
    """

    result = _llm_with_ref(
        [{"action_type": "MODIFY_GUIDE", "payload": {"change_type": "REPLACE_NODE",
                                                     "scope_hint": "DAY"}}],
        text="10月3号那天下雨了，换个室内的安排",
        reference=date(2026, 9, 24),
    )
    assert result.action.payload is not None
    assert result.action.payload.date == date(2026, 10, 3)


def test_model_given_date_wins_over_text_scanning() -> None:
    result = _llm_with_ref(
        [{"action_type": "MODIFY_GUIDE", "payload": {"change_type": "REPLACE_NODE",
                                                     "scope_hint": "DAY",
                                                     "date": "2026-10-04"}}],
        text="10月3号那天不方便",
        reference=date(2026, 9, 24),
    )
    assert result.action.payload is not None
    assert result.action.payload.date == date(2026, 10, 4)


def test_relative_day_wording_yields_no_date() -> None:
    """「第二天」这类相对说法不猜具体日期（契约要的是明确日期）。"""

    result = _llm_with_ref(
        [{"action_type": "MODIFY_GUIDE", "payload": {"change_type": "REMOVE_NODE",
                                                     "scope_hint": "DAY"}}],
        text="第二天上午的安排去掉",
        reference=date(2026, 9, 24),
    )
    assert result.action.payload is not None
    assert result.action.payload.date is None


def test_rule_based_path_also_resolves_short_dates() -> None:
    action = RuleBasedUserActionInterpreter().interpret(
        session_id=SESSION,
        text="把10月3号的安排改轻松点",
        known_node_ids=NODES,
        reference_date=date(2026, 9, 24),
    )
    assert action.payload is not None
    assert action.payload.date == date(2026, 10, 3)
