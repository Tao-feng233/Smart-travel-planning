"""提示词回归测试集（prompts-2026-09-28-v2 起）。

提示词是工程产物：每次改 `app/llm/prompts.py` 都要跑这个文件，
防止「修好 A 弄坏 B」。覆盖四层：

A. few-shot 示例本身的契约合法性（示例写坏了会直接把模型带沟里去）；
B. 组装后的 prompt 文本确实包含示例 / 决策清单 / 注入参数；
C. B5 解释器的 golden 用例 —— 模型按示例输出时我们能正确处理，
   模型掉链子时规则兜底仍能接住「把预算改成八千」这类高频修改；
D. 规则式兜底的 golden 话术（补充 `test_action_interpreter.py` 未覆盖的说法）。

全部离线运行（FakeLLMProvider / 规则兜底），不依赖任何真实 Key。
"""

from __future__ import annotations

import json
from datetime import date

from b_line_fakes import FakeLLMProvider

from app.llm.action_interpreter import (
    ACTION_TYPES,
    CHANGE_TYPES,
    SCOPE_HINTS,
    LLMUserActionInterpreter,
    RuleBasedUserActionInterpreter,
)
from app.llm.prompts import (
    B2_FEWSHOT_EXAMPLES,
    B4_FEWSHOT_EXAMPLE,
    B5_FEWSHOT_EXAMPLES,
    PROMPT_VERSION,
    _AVOIDANCE_TAGS,
    _DRAFT_SYSTEM_FIELDS,
    _INTEREST_TAGS,
    build_action_system_prompt,
    build_profile_system_prompt,
    build_recommend_system_prompt,
)
from app.schemas import TripProfileDraft

SESSION = "sess_prompt_regression"
NODES = ("node_001", "node_002", "node_arrive")
KNOWN_DESTINATIONS = {"大理": "dest_dali", "丽江": "dest_lijiang"}
REFERENCE_DATE = date(2026, 9, 28)


def _render(output: dict) -> str:
    """与 prompts._json_block 相同的渲染方式（示例必须逐字出现在 prompt 里）。"""

    return json.dumps(output, ensure_ascii=False, indent=2)


def _llm_interpret(payloads, *, text, node_ids=NODES):
    interpreter = LLMUserActionInterpreter(
        provider=FakeLLMProvider(*payloads)
    )
    return interpreter.interpret_with_diagnostics(
        session_id=SESSION,
        text=text,
        known_node_ids=node_ids,
        reference_date=REFERENCE_DATE,
    )


def _rules_interpret(text: str, *, reference_date: date | None = None):
    return RuleBasedUserActionInterpreter().interpret(
        session_id=SESSION,
        text=text,
        known_node_ids=NODES,
        reference_date=reference_date,
    )


# --- A. few-shot 示例的契约合法性 ---------------------------------------------


def test_b2_examples_validate_against_contract() -> None:
    assert len(B2_FEWSHOT_EXAMPLES) >= 2
    for user, output, note in B2_FEWSHOT_EXAMPLES:
        assert user.strip(), "示例必须带用户输入"
        assert note.strip(), "示例必须带讲解"
        draft = TripProfileDraft.model_validate({**output, "session_id": SESSION})
        assert draft.session_id == SESSION


def test_b2_examples_never_touch_system_fields() -> None:
    for _, output, _ in B2_FEWSHOT_EXAMPLES:
        leaked = set(output) & set(_DRAFT_SYSTEM_FIELDS)
        assert not leaked, f"示例出现了系统字段：{leaked}"


def test_b2_examples_use_only_normative_tags() -> None:
    allowed = set(_INTEREST_TAGS) | set(_AVOIDANCE_TAGS)
    for _, output, _ in B2_FEWSHOT_EXAMPLES:
        for tag in output.get("interests", []):
            assert tag in allowed, f"示例用了非规范兴趣标签：{tag}"
        for tag in output.get("avoidances", []):
            assert tag in allowed, f"示例用了非规范避讳标签：{tag}"


def test_b4_example_shape() -> None:
    output = B4_FEWSHOT_EXAMPLE["output"]
    recommendations = output.get("recommendations")
    assert isinstance(recommendations, list) and recommendations, "B4 示例必须给出至少一条推荐"
    for item in recommendations:
        assert set(item) <= {"destination_id", "suitable", "reason", "tradeoffs", "risk_flags"}
        assert isinstance(item["destination_id"], str) and item["destination_id"]
        # readiness_id / suggested_days / evidence_ids 由系统填写，示例里出现就是教坏模型
        assert "readiness_id" not in item
        assert "suggested_days" not in item
        assert "evidence_ids" not in item


def test_b5_examples_action_types_valid() -> None:
    assert len(B5_FEWSHOT_EXAMPLES) >= 3
    for _, output, _ in B5_FEWSHOT_EXAMPLES:
        assert output["action_type"] in ACTION_TYPES


def test_b5_examples_payload_enums_valid() -> None:
    for _, output, _ in B5_FEWSHOT_EXAMPLES:
        payload = output.get("payload")
        if payload is None:
            continue
        assert payload["change_type"] in CHANGE_TYPES
        assert payload["scope_hint"] in SCOPE_HINTS


def test_b5_examples_payload_presence_matches_action_type() -> None:
    for _, output, _ in B5_FEWSHOT_EXAMPLES:
        if output["action_type"] == "MODIFY_GUIDE":
            assert output.get("payload") is not None, "MODIFY_GUIDE 示例必须带 payload"
        else:
            assert output.get("payload") is None


# --- B. 组装后的 prompt 文本 ---------------------------------------------------


def test_prompt_version_recorded() -> None:
    assert PROMPT_VERSION.startswith("prompts-")
    import app.llm.prompts as prompts_module

    assert PROMPT_VERSION in (prompts_module.__doc__ or ""), "版本号必须写进模块变更记录"


def test_profile_prompt_renders_examples_verbatim() -> None:
    prompt = build_profile_system_prompt(
        reference_date=REFERENCE_DATE,
        known_destinations=KNOWN_DESTINATIONS,
        previous=None,
    )
    for user, output, _ in B2_FEWSHOT_EXAMPLES:
        assert f"用户说：{user}" in prompt
        assert _render(output) in prompt


def test_profile_prompt_injects_parameters() -> None:
    prompt = build_profile_system_prompt(
        reference_date=REFERENCE_DATE,
        known_destinations=KNOWN_DESTINATIONS,
        previous=None,
    )
    assert REFERENCE_DATE.isoformat() in prompt
    assert "大理 → dest_dali" in prompt
    assert "三条铁律" in prompt


def test_action_prompt_contains_decision_checklist() -> None:
    prompt = build_action_system_prompt(known_node_ids=NODES)
    assert "决策清单" in prompt
    # 「已有攻略时改预算算修改」是 v2 针对实测缺陷显式写入的判断信号
    assert "把预算改成八千" in prompt
    assert "MODIFY_GUIDE" in prompt


def test_action_prompt_renders_examples_and_nodes() -> None:
    prompt = build_action_system_prompt(known_node_ids=NODES)
    for node_id in NODES:
        assert node_id in prompt
    for user, output, _ in B5_FEWSHOT_EXAMPLES:
        assert f"用户说：{user}" in prompt
        assert _render(output) in prompt


def test_recommend_prompt_renders_example() -> None:
    prompt = build_recommend_system_prompt()
    assert "宁缺毋滥" in prompt
    assert _render(B4_FEWSHOT_EXAMPLE["output"]) in prompt


# --- C. B5 解释器 golden（模型按示例输出 → 我们正确处理） ----------------------


def test_golden_budget_modify_via_llm() -> None:
    """实测缺陷的靶向回归：「把预算改成八千」必须是 MODIFY_GUIDE + CHANGE_BUDGET。"""

    _, expected_output, _ = B5_FEWSHOT_EXAMPLES[1]
    result = _llm_interpret([expected_output], text="把预算改成八千")
    assert result.used_llm
    assert result.confident
    assert result.action.action_type == "MODIFY_GUIDE"
    assert result.action.payload is not None
    assert result.action.payload.change_type == "CHANGE_BUDGET"
    assert result.action.payload.scope_hint == "WHOLE_GUIDE"


def test_golden_confirm_via_llm() -> None:
    _, expected_output, _ = B5_FEWSHOT_EXAMPLES[0]
    result = _llm_interpret([expected_output], text="就这个吧，确认")
    assert result.action.action_type == "CONFIRM_GUIDE"
    assert result.action.payload is None


def test_golden_remove_node_via_llm() -> None:
    _, expected_output, _ = B5_FEWSHOT_EXAMPLES[2]
    result = _llm_interpret([expected_output], text="第二天那个博物馆不想去，去掉")
    assert result.action.payload is not None
    assert result.action.payload.change_type == "REMOVE_NODE"
    assert result.action.payload.target_node_ids == ["node_002"]
    assert result.confident


def test_llm_without_payload_falls_back_and_still_catches_budget() -> None:
    """模型没给 payload 时降级到规则兜底，「改预算」仍要被接住。"""

    result = _llm_interpret([{"action_type": "MODIFY_GUIDE"}], text="把预算改成八千")
    assert not result.used_llm
    assert not result.confident
    assert result.action.payload is not None
    assert result.action.payload.change_type == "CHANGE_BUDGET"


def test_out_of_contract_change_type_is_degraded() -> None:
    result = _llm_interpret(
        [
            {
                "action_type": "MODIFY_GUIDE",
                "payload": {"change_type": "MAKE_CHEAPER", "target_node_ids": []},
            }
        ],
        text="便宜一点",
    )
    assert result.used_llm
    assert not result.confident
    assert result.action.payload is not None
    assert result.action.payload.change_type == "REPLACE_NODE"


def test_out_of_range_node_id_is_discarded() -> None:
    result = _llm_interpret(
        [
            {
                "action_type": "MODIFY_GUIDE",
                "payload": {
                    "change_type": "REMOVE_NODE",
                    "scope_hint": "NODE",
                    "target_node_ids": ["node_999"],
                },
            }
        ],
        text="把博物馆去掉",
    )
    assert result.action.payload is not None
    assert result.action.payload.target_node_ids == []
    assert any("node_999" in item for item in result.diagnostics)


# --- D. 规则兜底 golden 话术（补充未覆盖的说法） -------------------------------


def test_rules_budget_rephrase() -> None:
    action = _rules_interpret("预算改成八千")
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_BUDGET"


def test_rules_short_date_change_uses_reference_year() -> None:
    action = _rules_interpret("推迟到10月3号", reference_date=REFERENCE_DATE)
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_DATE"
    assert action.payload.date == date(2026, 10, 3)


def test_rules_lodging_rephrase() -> None:
    action = _rules_interpret("住不惯，换个酒店")
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_LODGING"


def test_rules_add_node_rephrase() -> None:
    action = _rules_interpret("还想加一个古镇")
    assert action.payload is not None
    assert action.payload.change_type == "ADD_FIXED_NODE"


def test_rules_select_destination_rephrase() -> None:
    action = _rules_interpret("就选第一个")
    assert action.action_type == "SELECT_DESTINATION"
    assert action.payload is None


def test_rules_pace_with_whole_guide_scope() -> None:
    action = _rules_interpret("整体节奏慢一点")
    assert action.payload is not None
    assert action.payload.change_type == "CHANGE_PACE"
    assert action.payload.scope_hint == "WHOLE_GUIDE"
