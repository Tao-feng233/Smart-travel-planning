"""B2：LLM 需求提取（`LLMTripProfileParser`）测试。

覆盖三类场景（`AGENTS.md` 要求每个功能至少含正常、失败、数据不足）：
正常提取 / 模型不可用降级 / 输出越界与不合规时的拦截。
"""

from __future__ import annotations

from datetime import date

from b_line_fakes import FakeLLMProvider
from app.schemas import Money, TripProfileDraft, finalize_trip_profile
from app.llm.request_parser import LLMTripProfileParser, ParseOutcome

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


# --- 「N 天」时长与起止日期的口径 -------------------------------------------


def test_explicit_day_count_corrects_the_models_end_date() -> None:
    """用户明说的「玩 5 天」必须压过模型摇摆的推算。

    实测同一句话，模型会在 10-06（含首尾共 5 天）与 10-07（从出发日算 5 天）
    之间反复。多算一天会把 `duration_days` 从 5 抬到 6，而数据层按
    `2 * 天数 + 1` 算游玩地点覆盖门槛，足以把本来可规划的目的地判成不可规划。
    """

    payload = dict(_COMPLETE, end_date="2026-10-07")
    outcome = _outcome([payload], text="10月2号从上海出发去成都玩5天，2个人，预算5000元")

    assert outcome.draft.end_date == date(2026, 10, 6)
    assert finalize_trip_profile(outcome.draft).duration_days == 5
    assert any("5 天" in note and "修正" in note for note in outcome.diagnostics)


def test_explicit_days_fill_an_end_date_the_model_left_out() -> None:
    """模型没给返回日期、但文本写了「玩 5 天」时，返回日期要能补出来。"""

    payload = {key: value for key, value in _COMPLETE.items() if key != "end_date"}
    outcome = _outcome([payload], text="10月2号从上海出发去成都玩5天，2个人，预算5000元")

    assert outcome.draft.end_date == date(2026, 10, 6)
    assert finalize_trip_profile(outcome.draft).duration_days == 5


def test_two_stated_dates_win_over_a_day_count() -> None:
    """同时写了往返日期和「N 天」时以更具体的日期为准，规则不得替用户改口。"""

    payload = dict(_COMPLETE, end_date="2026-10-06")
    outcome = _outcome(
        [payload], text="10月2号到10月6号从上海出发去成都玩6天，2个人，预算5000元"
    )

    # 文本自相矛盾（2 号到 6 号含首尾共 5 天，却说玩 6 天）：日期更具体
    assert outcome.draft.end_date == date(2026, 10, 6)


def test_ordinal_day_word_is_not_read_as_a_duration() -> None:
    """「第一天」是日程叙述，不能被当成「1 天」的时长。"""

    payload = dict(_COMPLETE, end_date="2026-10-09")
    outcome = _outcome(
        [payload], text="10月2号从上海出发去成都，第一天想去宽窄巷子，预算5000元"
    )

    assert outcome.draft.end_date == date(2026, 10, 9)


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


# --- 越界目的地的结构化上报 ---------------------------------------------------
#
# B/C 联调约定：B2 把「用户提到、但不在知识库清单里」的目的地结构化报出来
# （`ParseOutcome.dropped_destinations`），C 线读它发
# `DESTINATION_OUT_OF_COVERAGE` 警告。
#
# 为什么不挂在 parser 实例上：`api/deps.py` 装配出的 parser 是**进程内单例**，
# 挂会话级状态在并发下必然串味。诊断是"这一轮"的信息，走返回值最自然。


def test_parse_outcome_defaults_to_empty_dropped() -> None:
    """新字段必须有默认值：老调用点（含降级路径）不改也不崩。"""

    outcome = ParseOutcome(draft=TripProfileDraft(session_id=SESSION), used_llm=False)

    assert outcome.dropped_destinations == ()


def test_out_of_catalog_destination_is_reported_structurally() -> None:
    """清单外的目的地要结构化上报：值是人能看懂的地名，不是诊断串。"""

    payload = dict(_COMPLETE)
    payload["departure_city"] = "上海"
    payload["destination_requests"] = [{"destination_id": "大理", "name": "大理"}]

    outcome = _outcome([payload], text="从上海出发去大理玩几天")

    # 上游要拿它当 WarningItem.details 的 key，所以必须是干净的结构化值
    assert outcome.dropped_destinations == ("大理",)
    # 人话诊断同时保留（排障用），两条通道各司其职
    assert any("大理" in item for item in outcome.diagnostics)
    # 越界目的地绝不进画像，也别谎报成 SINGLE
    assert outcome.draft.destination_requests == []
    assert outcome.draft.destination_mode == "UNKNOWN"


def test_out_of_catalog_destination_without_name_falls_back_to_identifier() -> None:
    """模型没给 name、只给了编造的 ID 时退回 ID —— 哪怕难看，也不替它编中文名。"""

    payload = dict(_COMPLETE)
    payload["destination_requests"] = [{"destination_id": "dest_dali"}]

    outcome = _outcome([payload])

    assert outcome.dropped_destinations == ("dest_dali",)


def test_out_of_catalog_notification_does_not_repeat() -> None:
    """同一个目的地被重复列出时只报一次，免得警告里堆重复条目。"""

    payload = dict(_COMPLETE)
    payload["destination_requests"] = [
        {"destination_id": "大理", "name": "大理"},
        {"destination_id": "大理", "name": "大理"},
    ]

    outcome = _outcome([payload])

    assert outcome.dropped_destinations == ("大理",)


def test_in_catalog_destination_is_not_reported_as_dropped() -> None:
    """清单内的目的地正常接受，绝不能被算进「被丢弃」。"""

    outcome = _outcome([_COMPLETE], text="就去成都")

    assert outcome.dropped_destinations == ()
    assert [item.name for item in outcome.draft.destination_requests] == ["成都"]


def test_destination_given_as_bare_string_is_reported_too() -> None:
    """模型把目的地写成裸字符串（`["大理"]`）时同样要上报。

    漏掉这条分支，模型换个写法就能让"用户提过的地方"再次静默消失，
    又回到老问题上。
    """

    payload = dict(_COMPLETE)
    payload["destination_requests"] = ["大理"]

    outcome = _outcome([payload])

    assert outcome.dropped_destinations == ("大理",)


def test_degraded_path_reports_nothing_dropped() -> None:
    """降级到规则式解析时 `dropped_destinations` 为空 —— 这是已知限制，不是 bug。

    越界目的地是"模型给了清单外 ID"才产生的，规则式解析器不产出这种 payload
    （它的候选本来就只从清单里挑）。所以**降级路径下"目的地暂不可规划"这条
    提示不会出现**。写进测试免得以后被当成回归，或被误认为已经全路径覆盖。
    """

    outcome = _outcome([_COMPLETE], available=False)

    assert outcome.used_llm is False
    assert outcome.dropped_destinations == ()


# --- 出发地不是目的地 ---------------------------------------------------------
#
# 实测暴露：「我从成都出发去大理」里的「成都」是出发点。模型偶尔会把出发地和
# 目的地都填进 `destination_requests`，下游就会排出一份"从成都出发去成都玩"的行程。


def test_departure_city_is_not_treated_as_destination() -> None:
    """同时存在出发城市和其它目的地时，丢掉被误填的出发地。"""

    payload = dict(_COMPLETE)
    payload["departure_city"] = "成都"
    payload["destination_requests"] = [
        {"destination_id": "dest_chengdu", "priority": "HIGH"},
        {"destination_id": "dest_leshan", "priority": "HIGH"},
    ]

    outcome = _outcome([payload], text="从成都出发去乐山玩")

    assert [item.name for item in outcome.draft.destination_requests] == ["乐山"]
    assert outcome.draft.destination_mode == "SINGLE"
    # 这是语义纠正、不是越界丢弃：不该给用户发"覆盖不足"警告
    assert outcome.dropped_destinations == ()
    assert any("出发地" in item for item in outcome.diagnostics)


def test_departure_city_is_kept_when_it_is_the_only_destination() -> None:
    """唯一一条目的地就是出发城市时保留：「就在成都玩」是合法需求，不能删。"""

    payload = dict(_COMPLETE)
    payload["departure_city"] = "成都"
    payload["destination_requests"] = [
        {"destination_id": "dest_chengdu", "priority": "HIGH"},
    ]

    outcome = _outcome([payload], text="就在成都玩几天")

    assert [item.name for item in outcome.draft.destination_requests] == ["成都"]


def test_departure_gate_leaves_other_destinations_untouched() -> None:
    """出发地不在知识库清单里时无从比对，不猜：目的地原样保留。"""

    payload = dict(_COMPLETE)
    payload["departure_city"] = "北京"
    payload["destination_requests"] = [
        {"destination_id": "dest_leshan", "priority": "HIGH"},
    ]

    outcome = _outcome([payload], text="从北京出发去乐山")

    assert [item.name for item in outcome.draft.destination_requests] == ["乐山"]
    assert outcome.dropped_destinations == ()
