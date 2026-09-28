"""`SendMessageData` 文案与降级说明测试。

回复文案是纯函数产物，所以可以直接断言「缺字段会问字段」
「缺住宿会说缺住宿」「排好行程会给预算区间」。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.graph.stages import PlanStage
from app.schemas import (
    BudgetSummary,
    Conflict,
    CostItem,
    DayPlan,
    ItineraryPlan,
    Money,
    PlanNode,
    PlanState,
    StaySegment,
    TripSegment,
    TripProfileDraft,
)
from app.services.reply_builder import build_reply

TZ = timezone(timedelta(hours=8))
START = date(2026, 10, 2)


def _draft() -> TripProfileDraft:
    return TripProfileDraft(session_id="sess_reply", departure_city="上海")


def _plan() -> ItineraryPlan:
    day = datetime.combine(START, datetime.min.time().replace(hour=9), tzinfo=TZ)
    node = PlanNode(
        node_id="node_1",
        node_type="ATTRACTION",
        resource_id="poi_1",
        start_at=day,
        end_at=day + timedelta(minutes=90),
        reason="示例",
    )
    stay = StaySegment(
        stay_segment_id="stay_1",
        check_in_date=START,
        check_out_date=START + timedelta(days=2),
        lodging_id="hotel_1",
        lodging_area="示例商圈",
    )
    segment = TripSegment(
        segment_id="seg_1",
        destination_id="dest_1",
        start_date=START,
        end_date=START + timedelta(days=1),
        allocated_days=2,
    )
    return ItineraryPlan(
        plan_id="plan_1",
        plan_version=1,
        session_id="sess_reply",
        timezone="Asia/Shanghai",
        start_date=START,
        end_date=START + timedelta(days=1),
        trip_segments=[segment],
        stay_segments=[stay],
        days=[
            DayPlan(
                date=START,
                segment_id=segment.segment_id,
                stay_segment_id=stay.stay_segment_id,
                node_ids=["node_1"],
                travel_leg_ids=[],
            ),
            DayPlan(
                date=START + timedelta(days=1),
                segment_id=segment.segment_id,
                stay_segment_id=stay.stay_segment_id,
                node_ids=["node_1"],
                travel_leg_ids=[],
            ),
        ],
        nodes=[node],
        travel_legs=[],
        cost_items=[
            CostItem(
                cost_item_id="cost_001",
                category="LODGING",
                item_ref="hotel_1",
                unit_price=Money(min_amount=1200, max_amount=1500, currency="CNY"),
                quantity=1,
                pricing_scope="PER_ROOM",
                status="ESTIMATED",
            )
        ],
        budget_summary=BudgetSummary(
            currency="CNY",
            total_limit=5000,
            known_total=0,
            estimated_min_total=1200,
            estimated_max_total=1500,
            remaining_min=3500,
            remaining_max=3800,
            by_category={"LODGING": 1200},
            unknown_cost_item_ids=[],
        ),
        plan_validation_status="PENDING",
        conflict_ids=[],
        data_snapshot_id="snap_1",
    )


def test_clarification_text_lists_questions() -> None:
    state = PlanState(session_id="sess_reply", stage=PlanStage.ASKING_CLARIFICATION.value)
    reply = build_reply(state, draft=_draft())
    assert "还需要确认" in reply.assistant_message
    assert "1." in reply.assistant_message
    assert reply.trip_profile is None


def test_insufficient_data_explains_what_is_missing() -> None:
    """缺关键数据时要说明缺什么，不能只丢一句"资料不足"。"""

    state = PlanState(session_id="sess_reply", stage=PlanStage.INSUFFICIENT_DATA.value)
    reply = build_reply(state, missing_inputs=["LODGING_CANDIDATES"])
    assert "住宿" in reply.assistant_message
    assert any("住宿" in item for item in reply.degraded_items)


def test_planning_reply_summarises_plan_and_conflicts() -> None:
    state = PlanState(session_id="sess_reply", stage=PlanStage.PLANNING.value)
    conflict = Conflict(
        conflict_id="c1",
        type="DATA_UNKNOWN",
        severity="WARNING",
        scope="COST",
        message="景点门票价格暂无数据。",
    )
    reply = build_reply(state, plan=_plan(), plan_conflicts=[conflict])
    assert "行程已排好" in reply.assistant_message
    assert "1500" in reply.assistant_message  # 预算上限来自计划，不是另算的
    assert "门票" in reply.assistant_message
    assert [item.conflict_id for item in reply.conflicts] == ["c1"]


def test_warning_details_carry_backend_question_text() -> None:
    """Q6 收尾：`details` 的 value 是**后端**的追问文案，前端不再抄一份。

    前端按「后端文案优先、本地兜底」渲染（B 已实现），所以后端一改文案，
    页面立刻跟着变——文案只有一份来源。
    """

    from app.services.reply_builder import build_warnings

    state = PlanState(session_id="sess_reply", stage=PlanStage.ASKING_CLARIFICATION.value)
    warnings = build_warnings(state, draft=_draft())
    item = next(w for w in warnings if w.code == "MISSING_PROFILE_FIELDS")
    assert set(item.details) == {"start_date", "end_date", "traveler_count", "budget"}
    assert "大概哪天出发" in item.details["start_date"]
    assert "预算" in item.details["budget"]


def test_out_of_coverage_destination_warning_shape() -> None:
    """用户点名知识库外的地方：warning 要有 code + 人话 message + 结构化 details。"""

    from app.services.reply_builder import build_warnings

    state = PlanState(session_id="sess_reply", stage=PlanStage.AWAITING_DESTINATION_CONFIRMATION.value)
    warnings = build_warnings(state, dropped_destinations=["大理"])
    item = next(w for w in warnings if w.code == "DESTINATION_OUT_OF_COVERAGE")
    assert "大理" in item.message
    assert item.details == {"大理": "不在知识库覆盖范围内"}


def test_awaiting_confirmation_asks_user_to_confirm() -> None:
    state = PlanState(
        session_id="sess_reply",
        stage=PlanStage.AWAITING_DESTINATION_CONFIRMATION.value,
        resource_candidate_ids=["poi_1"],
    )
    reply = build_reply(state, missing_inputs=[])
    assert "确认" in reply.assistant_message
