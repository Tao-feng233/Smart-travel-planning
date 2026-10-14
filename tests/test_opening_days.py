"""星期闭馆日判定：真实 opening 原文 -> 当天是否闭馆。

日期用固定值而非"今天+N"：这里的语义是"某年 11 月的周一"，因为资料里的月份
窗口（11月1日至次年4月30日 / 5月1日-10月31日）本身就带月份，换成相对日期会让
期望值随运行日期漂移。这些日期只喂给 closed_on / check / DailySchedule，
不进入任何"出游日不得早于今天"的校验（同 test_daily_schedule_boundaries 的用法）。
"""

import asyncio
import copy
from datetime import date
from types import SimpleNamespace

import pytest

from app.planning import opening_days as od
from app.planning import opening_hours as oh

# 全部取自高德 opening 原文
GLOBAL_RULE = (
    "周一闭馆 国家法定节假日除外；11月1日至次年4月30日 周二至周日 09:00-16:30(16:00停止入馆)；"
    "5月1日-10月31日 09:00-17:00 (16:30停止入馆)"
)
PURE_WEEK = "周一全天关闭（法定节假日除外），周二至周日:9:00-18:00"
WINDOWED_WEEK = "4月1日-10月31日:09:00-17:30；11月1日-3月31日:周二-周日:09:00-17:30"
FULL_WEEK = "1月至4月,11月至12月 周一至周日 08:30-17:30 最晚进入16:30"
DATE_EXCEPTION = "全年 09:00–17:30开放 最晚售票16:30 最晚进入17:00；除夕 全天不开放"

MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)

# --- 逐条形态 × 周一/周二/周三 ----


@pytest.mark.parametrize(
    "name,opening,monday,tuesday,wednesday",
    [
        ("全局星期规则+月份窗口+时段", GLOBAL_RULE, True, False, False),
        ("纯星期规则无月份窗口", PURE_WEEK, True, False, False),
        ("月份窗口内才带星期规则", WINDOWED_WEEK, True, False, False),
        ("周一至周日=全周开放", FULL_WEEK, False, False, False),
        ("全年开放+除夕例外（不生效）", DATE_EXCEPTION, None, None, None),
    ],
)
def test_closed_on_real_opening_texts(name, opening, monday, tuesday, wednesday):
    assert od.closed_on(opening, MON) is monday, name
    assert od.closed_on(opening, TUE) is tuesday, name
    assert od.closed_on(opening, WED) is wednesday, name


def test_week_range_is_expanded_not_just_its_endpoints():
    # "周二至周日" 是 1..6，不是只有 {周二, 周日}
    rules = od.rules_of(PURE_WEEK)
    opens = [r["open"] for r in rules if r.get("open")]
    assert opens and opens[0] == {1, 2, 3, 4, 5, 6}


def test_month_window_limits_the_week_rule():
    # 星期词只绑定它之前最近的那个月份窗口，不能把夏季规则套到冬季
    week_rules = [r for r in od.rules_of(WINDOWED_WEEK) if not r.get("unrestricted")]
    assert len(week_rules) == 1
    assert week_rules[0]["months"] == (11, 1, 3, 31)


def test_same_text_opposite_verdicts_in_two_months():
    # 同一条原文，4/1-10/31 段没有星期限制、11/1-3/31 段是周二至周日：
    # 夏季周一照常开门，冬季周一关门。这一对是月份敏感性的最小充分证据。
    assert od.closed_on(WINDOWED_WEEK, date(2026, 7, 6)) is False
    assert od.closed_on(WINDOWED_WEEK, date(2026, 11, 2)) is True


def test_week_rule_is_not_applied_to_the_wrong_month_window():
    # 陕西历史博物馆：句末"周一全天关闭"属于 11/15 起的窗口，
    # 不得套到 4/1-11/14 段上；11-02/03/04 全落前一段，应判开放。
    text = ("4月1日至11月14日 08:30-19:00 (18:00停止检票),"
            "11月15日至3月14日周一 全天关闭(法定节假日除外), 周二至周日09:00-17:00")
    for day in (MON, TUE, WED):
        assert od.closed_on(text, day) is not True, day


def test_weekday_list_with_a_lone_entry_is_read_as_open():
    # "周一,周三至周日" 是开放日枚举，周一写在里面就是开放；
    # 只取"周三至周日"会反过来把周一判成闭馆（实测误拦）。
    assert od.closed_on("周一,周三至周日 08:30-18:00", MON) is False
    assert od.closed_on("周一,周三至周日 08:30-18:00", TUE) is True


def test_full_week_marker_never_means_closed():
    # "周一至周日" 是天天开，最容易被读成"周一闭馆"
    assert od.closed_on(FULL_WEEK, MON) is False


def test_a_closed_day_does_not_spill_onto_the_other_weekdays():
    # 只写"周一闭馆"时，周二不是闭馆日，而是"没说" —— 没说就不能拦。
    # 反过来看：这条同时也是"拿不到信息时返回 True"这种改法的照妖镜。
    assert od.closed_on("周一闭馆", MON) is True
    assert od.closed_on("周一闭馆", TUE) is None
    assert od.closed_on("周一闭馆", WED) is None
    assert oh.check("周一闭馆", "某馆", 10 * 60, 120, TUE)[0]


def test_particular_date_exception_is_not_read_as_a_weekday_rule():
    # "除夕 全天不开放" 没有星期词，不能退化成"全年闭馆"
    assert od.rules_of(DATE_EXCEPTION) == []
    assert od.closed_on(DATE_EXCEPTION, MON) is None


@pytest.mark.parametrize(
    "opening",
    ["周一至周日 00:00-24:00", "09:00-17:00", "", None, "请以景区公告为准"],
)
def test_no_weekday_information_never_blocks(opening):
    # 保守优先：读不出星期信息就当不知道，宁可漏拦也不误拦
    assert od.closed_on(opening, MON) in (False, None)
    assert oh.check(opening, "某景点", 10 * 60, 120, MON)[0]


def test_closure_strength_separates_explicit_from_inferred():
    # 明文"周一闭馆"是 explicit；"周二至周日"里没列出周一是 inferred。
    # 后者是推断，不能当明示结论用，所以必须能在返回值里区分开。
    assert od.closure_strength("周一闭馆", MON) == "explicit"
    assert od.closure_strength(WINDOWED_WEEK, MON) == "inferred"
    assert od.closure_strength("08:00-17:00", MON) is None
    assert "推断" in od.closed_reason(WINDOWED_WEEK, MON)
    assert "推断" not in od.closed_reason("周一闭馆", MON)


def test_check_without_a_day_keeps_the_old_behaviour():
    # 不传日期时，行为与改造前完全一致（C5 原来的零告警也是这个路径）
    ok, why, limit = oh.check(GLOBAL_RULE, "青岛市博物馆", 14 * 60 + 15, 120)
    assert (ok, why) == (True, "")
    assert limit == 17 * 60


def test_check_on_a_closed_day_refuses_with_zero_available_time():
    ok, why, limit = oh.check(GLOBAL_RULE, "青岛市博物馆", 14 * 60 + 15, 120, MON)
    assert not ok and "周一" in why and "不开放" in why
    assert limit == 0
    # 法定节假日但书必须带进提示，不让用户当成确定结论
    assert "法定节假日除外" in why
    assert oh.check(GLOBAL_RULE, "青岛市博物馆", 10 * 60, 60, TUE)[0]


# C5 那次真实跑里 get_spot_candidates 返回的 opening_week 原文（青岛市博物馆）
C5_MUSEUM = (
    "周一闭馆 国家法定节假日除外；11月1日至次年4月30日 周二至周日 09:00-16:30(16:00停止入馆)；"
    "5月1日-10月31日 09:00-17:00 (16:30停止入馆)"
)


def test_c5_museum_monday_is_closed_and_marked_explicit():
    assert od.closed_on(C5_MUSEUM, date(2026, 11, 2)) is True
    assert od.closure_strength(C5_MUSEUM, date(2026, 11, 2)) == "explicit"


def test_c5_museum_tuesday_is_open():
    assert od.closed_on(C5_MUSEUM, date(2026, 11, 3)) is False


@pytest.mark.xfail(
    strict=True,
    reason=("冬令时 16:30 未生效：parse() 取所有时段的并集得 17:00（既有设计，"
            "见 opening_hours 模块 docstring 与 test_seasonal_ranges_use_union_and_"
            "tightest_last_entry）。要按月份挑时段属于新改动，待裁定。"),
)
def test_c5_museum_winter_closing_time_is_1630_not_1700():
    assert oh.allowed_end(C5_MUSEUM, "青岛市博物馆") == 16 * 60 + 30


def test_c5_museum_monday_rule_survives_the_summer_window():
    # 7 月的周一落在夏令时窗口里，但"周一闭馆"是全年规则，不能被月份窗口吃掉
    assert od.closed_on(C5_MUSEUM, date(2026, 7, 6)) is True
    assert od.closure_strength(C5_MUSEUM, date(2026, 7, 6)) == "explicit"


def test_c5_museum_summer_tuesday_closes_at_1700():
    assert od.closed_on(C5_MUSEUM, date(2026, 7, 7)) is False
    assert oh.allowed_end(C5_MUSEUM, "青岛市博物馆") == 17 * 60


def test_c5_museum_monday_rule_is_universal_not_bucketted_into_a_window():
    # A 裁定的结构级证据：位于月份窗口左侧、自身不带月份限定词的星期规则
    # 必须判为全年规则（months is None），不能进冬令窗口的桶
    closed_rules = [r for r in od.rules_of(C5_MUSEUM) if r.get("closed")]
    assert len(closed_rules) == 1
    assert closed_rules[0]["months"] is None
    assert closed_rules[0]["closed"] == {0}
    # 冬令窗口里那条是"周二至周日开放"，星期一不在里面，两条互不干扰
    assert [r["months"] for r in od.rules_of(C5_MUSEUM)] == [None, (11, 1, 4, 30), (5, 1, 10, 31)]


def test_universal_monday_rule_does_not_depend_on_the_semicolon_separator():
    # 同一句话改用逗号断句（不靠「；」切成独立片段）时，周一闭馆仍是全年规则
    comma = C5_MUSEUM.replace("；", "，")
    assert od.closed_on(comma, date(2026, 7, 6)) is True
    assert od.closure_strength(comma, date(2026, 7, 6)) == "explicit"
    assert od.closed_on(comma, date(2026, 11, 2)) is True


def test_monday_closure_written_after_a_window_is_bound_to_that_window():
    # 对照组：周一闭馆写在月份窗口之后，属于该窗口，不得外溢成全年规则
    text = ("11月1日至次年4月30日 周二至周日 09:00-16:30(16:00停止入馆) 周一闭馆；"
            "5月1日-10月31日 09:00-17:00 (16:30停止入馆)")
    assert od.closed_on(text, date(2026, 11, 2)) is True
    assert od.closed_on(text, date(2026, 7, 6)) is False


def _schedule(day, opening):
    """走 DailySchedule 真实链路，返回 (排入的景点, 边界告警)。"""
    from app.planning.daily_schedule import DailySchedule
    from app.planning.plan_context import PlanContext

    point = {"id": "museum", "kind": "spot", "name": "青岛市博物馆", "opening": opening}
    workspace = {
        "requirements": {"city": "青岛", "start_date": day, "days": 1, "day_start": "14:00"},
        "catalog": {point["id"]: point},
        "selected_spots": [point["id"]],
    }
    before = copy.deepcopy(workspace)
    ctx = PlanContext(workspace, lambda _: None, True, SimpleNamespace())
    ctx.requirements = workspace["requirements"]
    ctx.catalog = workspace["catalog"]
    ctx.routes = {}
    ctx.return_time = None
    asyncio.run(
        DailySchedule(
            ctx, {"date": day, "items": [{"candidate_id": "museum", "duration": 120}]}
        ).build()
    )
    assert workspace == before, "排程不得改动用户已选内容"
    return (
        [e for e in ctx.computed[0]["events"] if e["kind"] == "spot"],
        ctx.boundary_issues,
    )


def test_closed_day_is_warned_and_not_written_into_the_plan():
    # 缺陷现场：C5 把青岛市博物馆排在周一 14:15，零告警
    visits, issues = _schedule("2026-11-02", GLOBAL_RULE)
    assert not visits
    assert [i["code"] for i in issues] == ["opening_hours"]
    assert issues[0]["available_minutes"] == 0
    # code 复用 opening_hours，靠这些字段把"闭馆"和"超出开放时段"区分开，
    # 并标出证据强度：青岛市博物馆原文有"周一闭馆"四个字，是 explicit
    assert issues[0]["closed_on_weekday"] is True
    assert issues[0]["closure_strength"] == "explicit"


def test_overrun_warning_does_not_carry_the_closed_day_flag():
    # 同一条通道：超出开放时段的告警不能带闭馆标记，否则无法归因
    _, issues = _schedule("2026-11-03", "09:00-11:00")
    assert [i["code"] for i in issues] == ["opening_hours"]
    assert "closed_on_weekday" not in issues[0]


def test_open_day_is_still_scheduled():
    visits, _ = _schedule("2026-11-03", GLOBAL_RULE)
    assert visits and visits[0]["name"] == "青岛市博物馆"
