"""REST 接口测试（v0.4 统一响应信封）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import build_session_service, get_session_service
from app.main import create_app
from app.services.session_store import InMemorySessionRepository

TRIP_TEXT = "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食"


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    service = build_session_service(repository=InMemorySessionRepository())
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)


def _create(client: TestClient, run_mode: str = "DEMO") -> str:
    response = client.post("/api/sessions", json={"run_mode": run_mode})
    assert response.status_code == 201
    return response.json()["data"]["session_id"]


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_session_returns_envelope_and_state(client: TestClient) -> None:
    response = client.post("/api/sessions", json={"run_mode": "DEMO"})
    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert body["trace_id"].startswith("trace_")
    assert body["data"]["session_id"].startswith("sess_")
    assert body["data"]["state"]["stage"] == "CREATED"
    assert body["data"]["state"]["session_id"] == body["data"]["session_id"]


def test_create_session_requires_run_mode(client: TestClient) -> None:
    """`run_mode` 是契约必填字段，缺失时请求体非法。"""

    assert client.post("/api/sessions", json={}).status_code == 422


def test_message_round_trip_asks_then_recommends(client: TestClient) -> None:
    session_id = _create(client)

    first = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "我想出去玩"}
    )
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert first_data["stage"] == "ASKING_CLARIFICATION"
    assert "还需要确认" in first_data["assistant_message"]
    assert "大概哪天出发" in first_data["assistant_message"]

    second = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": TRIP_TEXT}
    )
    second_body = second.json()
    assert second_body["data"]["stage"] == "AWAITING_DESTINATION_CONFIRMATION"
    candidates = second_body["data"]["destination_candidates"]
    assert candidates and candidates[0]["destination_id"] == "dest_chengdu"
    assert candidates[0]["evidence_ids"]
    assert "成都" in second_body["data"]["assistant_message"]
    assert second_body["data"]["trip_profile"]["duration_days"] == 5


def test_named_destination_is_prefiltered_before_planning(client: TestClient) -> None:
    """C3：点名目的地后，不可用资源在回复里被明确排除并说明原因。"""

    session_id = _create(client)
    body = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": TRIP_TEXT + "，想去成都"},
    ).json()
    state = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert body["data"]["stage"] == "AWAITING_DESTINATION_CONFIRMATION"
    assert "poi_1002" not in state["resource_candidate_ids"]
    assert state["resource_candidate_ids"]
    assert "已排除 poi_1002" in body["data"]["assistant_message"]


def test_mock_data_is_announced_exactly_once(client: TestClient) -> None:
    """模拟数据必须显式告知，且不能同一条重复两三遍。"""

    session_id = _create(client)
    body = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "随便看看"}
    ).json()
    mock_warnings = [item for item in body["warnings"] if item["code"] == "MOCK_DATA_IN_DEMO"]
    assert len(mock_warnings) == 1
    assert "模拟数据" in mock_warnings[0]["message"]
    # degraded_items 不再重复同一条，只放本轮额外的降级项
    assert not [item for item in body["data"]["degraded_items"] if "模拟数据" in item]


def test_get_session_returns_state_and_missing_field_warning(
    client: TestClient,
) -> None:
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/messages", json={"text": "我想出去玩"})
    body = client.get(f"/api/sessions/{session_id}").json()
    # 关键字段未补齐时不会生成正式 TripProfile，缺失信息挂在 warning 上
    assert body["data"]["trip_profile_version"] == 0
    assert body["data"]["stage"] == "ASKING_CLARIFICATION"
    assert "MISSING_PROFILE_FIELDS" in [item["code"] for item in body["warnings"]]


def test_stale_expected_profile_version_returns_409(client: TestClient) -> None:
    session_id = _create(client)
    client.post(f"/api/sessions/{session_id}/messages", json={"text": TRIP_TEXT})
    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "预算改成8000元", "expected_profile_version": 99},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["ok"] is False
    assert detail["error"]["code"] == "VERSION_CONFLICT"


def test_unknown_session_returns_404_with_error_detail(client: TestClient) -> None:
    response = client.post(
        "/api/sessions/sess_missing/messages", json={"text": "你好"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "DATA_MISSING"
    assert client.get("/api/sessions/sess_missing").status_code == 404


def test_empty_message_is_rejected_by_schema(client: TestClient) -> None:
    session_id = _create(client)
    # text 缺失属于请求体非法
    assert client.post(f"/api/sessions/{session_id}/messages", json={}).status_code == 422
