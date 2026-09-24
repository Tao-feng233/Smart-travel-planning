"""REST 接口测试（C2 的接口部分）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import build_session_service, get_session_service
from app.main import create_app
from app.services.session_store import InMemorySessionRepository


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    service = build_session_service(repository=InMemorySessionRepository())
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_session(client: TestClient) -> None:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "CREATED"
    assert body["session_id"].startswith("sess_")


def test_message_round_trip_asks_then_recommends(client: TestClient) -> None:
    session_id = client.post("/api/sessions").json()["session_id"]

    first = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "我想出去玩"}
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["stage"] == "ASKING_CLARIFICATION"
    assert first_body["awaiting_user_input"] is True
    assert first_body["reply"]["kind"] == "QUESTION"
    assert first_body["reply"]["questions"]

    second = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食"},
    )
    second_body = second.json()
    assert second_body["stage"] == "AWAITING_DESTINATION_CONFIRMATION"
    assert second_body["reply"]["kind"] == "RECOMMENDATION"
    suggestions = second_body["reply"]["suggestions"]
    assert suggestions and suggestions[0]["name"] == "成都"
    assert suggestions[0]["evidence_ids"]


def test_mock_data_is_announced_to_the_frontend(client: TestClient) -> None:
    """模拟数据必须显式告知，不得静默当成真实数据。"""

    session_id = client.post("/api/sessions").json()["session_id"]
    body = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "随便看看"}
    ).json()
    assert body["reply"]["notes"]
    assert "模拟数据" in body["reply"]["notes"][0]


def test_get_session_returns_current_state(client: TestClient) -> None:
    session_id = client.post("/api/sessions").json()["session_id"]
    client.post(f"/api/sessions/{session_id}/messages", json={"text": "我想出去玩"})
    response = client.get(f"/api/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["state"]["profile"]["missing_fields"]


def test_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/sessions/sess_missing/messages", json={"text": "你好"}
    )
    assert response.status_code == 404
    assert client.get("/api/sessions/sess_missing").status_code == 404


def test_empty_message_is_rejected_by_schema(client: TestClient) -> None:
    session_id = client.post("/api/sessions").json()["session_id"]
    # text 缺失属于请求体非法
    assert client.post(f"/api/sessions/{session_id}/messages", json={}).status_code == 422
