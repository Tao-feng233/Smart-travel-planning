"""B4：LLM 目的地推荐（`LLMDestinationRecommender`）测试。

重点不是「模型推荐得好不好」，而是**越界与编造能不能被拦住**：
集合外的 ID、含未经核验事实的理由、没有理由的推荐，都必须出不来。
"""

from __future__ import annotations

from datetime import date

from b_line_fakes import FakeKnowledgeProvider, FakeLLMProvider, make_evidence
from app.schemas import (
    DestinationRecommendation,
    Money,
    TravelerComposition,
    TripProfile,
)
from app.llm.destination_recommender import LLMDestinationRecommender

EVIDENCE = {
    "dest_chengdu": [
        make_evidence("ev_101", "dest_chengdu", "成都适合慢节奏城市漫步与美食体验。"),
        make_evidence("ev_102", "dest_chengdu", "城市人文气息浓厚，片区之间通勤可控。"),
    ],
    "dest_leshan": [
        make_evidence("ev_201", "dest_leshan", "乐山以美食与小城人文见长。"),
    ],
}


def _profile() -> TripProfile:
    return TripProfile(
        session_id="sess_b4",
        departure_city="上海",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 6),
        duration_days=5,
        traveler_count=2,
        traveler_composition=TravelerComposition(adults=2),
        budget=Money(amount=5000),
        budget_flexibility="NEGOTIABLE",
        pace="RELAXED",
        interests=["FOOD", "CULTURE"],
        destination_mode="SINGLE",
    )


def _candidates() -> list[DestinationRecommendation]:
    return [
        DestinationRecommendation(
            destination_id="dest_chengdu",
            readiness_id="ready_chengdu_1",
            suggested_days=5,
            reason="覆盖达标",
            evidence_ids=["ev_101"],
        ),
        DestinationRecommendation(
            destination_id="dest_leshan",
            readiness_id="ready_leshan_1",
            suggested_days=2,
            reason="覆盖达标",
            evidence_ids=["ev_201"],
        ),
    ]


def _recommend(payloads, *, available=True, error=None, **kwargs):
    recommender = LLMDestinationRecommender(
        provider=FakeLLMProvider(*payloads, available=available, error=error), **kwargs
    )
    return recommender.recommend_with_diagnostics(
        profile=_profile(),
        candidates=_candidates(),
        readiness=[],
        mcp=FakeKnowledgeProvider(EVIDENCE),
    )


# --- 正常场景 ---------------------------------------------------------------


def test_llm_recommends_within_the_candidate_set() -> None:
    payload = {
        "recommendations": [
            {
                "destination_id": "dest_chengdu",
                "suitable": True,
                "reason": "资料显示它适合慢节奏的城市漫步与美食体验",
                "tradeoffs": ["可核验资料较少"],
                "risk_flags": [],
            }
        ]
    }
    outcome = _recommend([payload])
    assert outcome.used_llm is True
    assert len(outcome.recommendations) == 1

    item = outcome.recommendations[0]
    assert item.destination_id == "dest_chengdu"
    # 这三个字段一律由系统填，不采信模型
    assert item.readiness_id == "ready_chengdu_1"
    assert item.evidence_ids == ["ev_101", "ev_102"]
    assert item.suggested_days == 5


def test_suggested_days_is_clamped_to_the_trip_length() -> None:
    payload = {
        "recommendations": [
            {"destination_id": "dest_chengdu", "reason": "资料与偏好相符"}
        ]
    }
    outcome = _recommend([payload])
    assert outcome.recommendations[0].suggested_days <= _profile().duration_days


def test_thin_evidence_gets_a_risk_flag() -> None:
    payload = {
        "recommendations": [
            {"destination_id": "dest_leshan", "reason": "资料与偏好相符"}
        ]
    }
    outcome = _recommend([payload])
    assert "LIMITED_EVIDENCE" in outcome.recommendations[0].risk_flags


# --- 红线拦截 ---------------------------------------------------------------


def test_out_of_candidate_destination_is_rejected() -> None:
    payload = {
        "recommendations": [
            {"destination_id": "dest_beijing", "reason": "首都，非常值得去"},
            {"destination_id": "dest_chengdu", "reason": "资料与偏好相符"},
        ]
    }
    outcome = _recommend([payload])
    assert [item.destination_id for item in outcome.recommendations] == ["dest_chengdu"]
    assert any("候选集合外" in note for note in outcome.diagnostics)


def test_reason_with_unverified_facts_is_rejected() -> None:
    """理由里出现具体时刻、票价这类事实表述 → 整条推荐丢掉。"""

    payload = {
        "recommendations": [
            {
                "destination_id": "dest_chengdu",
                "reason": "这里有 08:30 开门，门票 120 元，非常划算",
            }
        ]
    }
    outcome = _recommend([payload])
    assert outcome.used_llm is False  # 唯一一条被拦掉 → 降级到规则式
    assert any("未经核验的事实表述" in note for note in outcome.diagnostics)


def test_recommendation_without_reason_is_rejected() -> None:
    payload = {"recommendations": [{"destination_id": "dest_chengdu", "reason": ""}]}
    outcome = _recommend([payload])
    assert outcome.used_llm is False
    assert any("没有理由" in note for note in outcome.diagnostics)


def test_tradeoff_with_facts_is_dropped_but_keeps_the_recommendation() -> None:
    payload = {
        "recommendations": [
            {
                "destination_id": "dest_chengdu",
                "reason": "资料与偏好相符",
                "tradeoffs": ["打车约 30 元", "可核验资料较少"],
            }
        ]
    }
    outcome = _recommend([payload])
    assert outcome.used_llm is True
    assert outcome.recommendations[0].tradeoffs == ["可核验资料较少"]
    assert any("取舍含事实表述" in note for note in outcome.diagnostics)


def test_duplicate_recommendations_are_deduplicated() -> None:
    payload = {
        "recommendations": [
            {"destination_id": "dest_chengdu", "reason": "资料与偏好相符"},
            {"destination_id": "dest_chengdu", "reason": "资料与偏好相符"},
        ]
    }
    outcome = _recommend([payload])
    assert len(outcome.recommendations) == 1


def test_malformed_payload_shape_is_rejected() -> None:
    outcome = _recommend([{"recommendations": "成都更好"}])
    assert outcome.used_llm is False
    assert any("不是数组" in note for note in outcome.diagnostics)


# --- 数据不足 / 降级场景 ----------------------------------------------------


def test_no_evidence_means_no_recommendation_at_all() -> None:
    """一个候选都拿不到证据时，宁可不推荐，也不能靠模型记忆补理由。"""

    recommender = LLMDestinationRecommender(
        provider=FakeLLMProvider(
            {"recommendations": [{"destination_id": "dest_chengdu", "reason": "就是好"}]}
        )
    )
    outcome = recommender.recommend_with_diagnostics(
        profile=_profile(),
        candidates=_candidates(),
        readiness=[],
        mcp=FakeKnowledgeProvider({}),
    )
    assert outcome.recommendations == []
    assert outcome.used_llm is False
    assert any("检索不到可核验证据" in note for note in outcome.diagnostics)


def test_provider_failure_degrades_to_the_rule_based_stub() -> None:
    outcome = _recommend([], error=RuntimeError("网关 502"))
    assert outcome.used_llm is False
    assert any("降级为规则式推荐" in note for note in outcome.diagnostics)
    assert {item.destination_id for item in outcome.recommendations} <= {
        "dest_chengdu",
        "dest_leshan",
    }


def test_unavailable_provider_degrades_to_the_rule_based_stub() -> None:
    outcome = _recommend([], available=False)
    assert outcome.used_llm is False
    assert outcome.recommendations != []
    assert any("降级为规则式推荐" in note for note in outcome.diagnostics)


def test_max_results_is_respected() -> None:
    payload = {
        "recommendations": [
            {"destination_id": "dest_chengdu", "reason": "资料与偏好相符"},
            {"destination_id": "dest_leshan", "reason": "资料与偏好相符"},
        ]
    }
    outcome = _recommend([payload], max_results=1)
    assert len(outcome.recommendations) == 1
