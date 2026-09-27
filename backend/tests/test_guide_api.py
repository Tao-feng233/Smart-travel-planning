"""C7 攻略接口测试（`CONTRACTS.md` §13.2）。

用 `test_graph_planning` 的假 Provider（带住宿、路线、城际、室内备选），
所以这里验证的是接口与组装链路；A 的数据到位后换成真实 Provider 即可。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import build_session_service, get_session_service
from app.main import create_app
from app.services.session_store import InMemorySessionRepository
from test_graph_planning import TRIP_TEXT, _deps

SECTIONS = (
    "trip_summary",
    "arrival_and_departure",
    "preparation",
    "lodging",
    "daily_itinerary",
    "budget_and_alternatives",
    "sources_and_freshness",
)


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    service = build_session_service(
        repository=InMemorySessionRepository(), node_deps=_deps()
    )
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)


def _reach_guide(client: TestClient) -> tuple[str, dict]:
    session_id = client.post("/api/sessions", json={"run_mode": "DEMO"}).json()["data"][
        "session_id"
    ]
    client.post(f"/api/sessions/{session_id}/messages", json={"text": TRIP_TEXT})
    body = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "确认"}
    ).json()
    return body["data"]["guide_id"], body["data"]


def test_guide_endpoint_returns_seven_sections(client: TestClient) -> None:
    guide_id, reply = _reach_guide(client)
    assert guide_id, "确认后应当组装出攻略"
    assert reply["stage"] == "READY"
    assert reply["guide_id"] == guide_id

    response = client.get(f"/api/guides/{guide_id}")
    assert response.status_code == 200
    body = response.json()
    guide = body["data"]["travel_guide"]
    for section in SECTIONS:
        assert section in guide, f"攻略缺少 {section}"
    assert guide["daily_itinerary"], "每日行程不能为空"
    assert guide["arrival_and_departure"]["arrival_plan"]["duration_minutes"] > 0
    assert guide["plan_validation_status"] == "VALID"


def test_confirm_is_idempotent_with_same_key(client: TestClient) -> None:
    """同一个幂等键重复提交：返回上次结果，不再升版本（A 线联调提过）。"""

    guide_id, _ = _reach_guide(client)
    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    payload = {
        "expected_guide_version": guide["guide_version"],
        "lock_node_ids": [],
        "idempotency_key": "same-key-1",
    }
    first = client.post(f"/api/guides/{guide_id}/confirm", json=payload).json()["data"][
        "travel_guide"
    ]
    second = client.post(f"/api/guides/{guide_id}/confirm", json=payload).json()["data"][
        "travel_guide"
    ]
    assert second["guide_version"] == first["guide_version"]


def test_unknown_guide_returns_404(client: TestClient) -> None:
    response = client.get("/api/guides/guide_does_not_exist")
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "DATA_MISSING"


def test_confirm_locks_nodes_and_bumps_guide_version(client: TestClient) -> None:
    guide_id, _ = _reach_guide(client)
    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    node_id = guide["daily_itinerary"][0]["nodes"][0]["node_id"]

    response = client.post(
        f"/api/guides/{guide_id}/confirm",
        json={
            "expected_guide_version": guide["guide_version"],
            "lock_node_ids": [node_id],
            "idempotency_key": "confirm-1",
        },
    )
    assert response.status_code == 200
    confirmed = response.json()["data"]["travel_guide"]
    assert confirmed["lifecycle_status"] == "CONFIRMED"
    assert confirmed["guide_version"] == guide["guide_version"] + 1
    assert any(
        node["locked"]
        for day in confirmed["daily_itinerary"]
        for node in day["nodes"]
    ), "锁定节点必须体现在攻略里"


def test_stale_guide_version_returns_409(client: TestClient) -> None:
    guide_id, _ = _reach_guide(client)
    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    client.post(
        f"/api/guides/{guide_id}/confirm",
        json={
            "expected_guide_version": guide["guide_version"],
            "lock_node_ids": [],
            "idempotency_key": "confirm-1",
        },
    )
    stale = client.post(
        f"/api/guides/{guide_id}/confirm",
        json={
            "expected_guide_version": guide["guide_version"],
            "lock_node_ids": [],
            "idempotency_key": "confirm-2",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"]["code"] == "VERSION_CONFLICT"


def test_incident_endpoint_replans_and_bumps_versions(client: TestClient) -> None:
    guide_id, _ = _reach_guide(client)
    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    response = client.post(
        f"/api/guides/{guide_id}/incident",
        json={
            "action": {
                "action_id": "act_rain_1",
                "action_type": "REPORT_INCIDENT",
                "session_id": guide["session_id"],
                "guide_id": guide_id,
                "expected_guide_version": guide["guide_version"],
                "raw_text": "今天下雨了",
            }
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["travel_guide"]["guide_version"] == guide["guide_version"] + 1
    assert data["version_lineage"]["parent_plan_version"] is not None
    assert data["version_lineage"]["new_plan_version"] > data["version_lineage"]["parent_plan_version"]


def test_unsupported_modification_is_reported_honestly(client: TestClient) -> None:
    """P0 不支持的改动（改日期）要明确报错，不能假装成功。"""

    guide_id, _ = _reach_guide(client)
    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    response = client.post(
        f"/api/guides/{guide_id}/modify",
        json={
            "action": {
                "action_id": "act_change_date",
                "action_type": "MODIFY_GUIDE",
                "session_id": guide["session_id"],
                "guide_id": guide_id,
                "expected_guide_version": guide["guide_version"],
                "payload": {
                    "change_type": "CHANGE_DATE",
                    "scope_hint": "WHOLE_GUIDE",
                },
            }
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "DATA_MISSING"


def _assert_history_and_lineage(client: TestClient, guide_id: str, guide: dict) -> None:
    """B 报的三处缺口：历史版本可查 / 会话返回 guide_id / 谱系带攻略版本。"""

    # 1) 会话详情必须带 guide_id（刷新页面后前端要靠它找攻略）
    session_id = guide["session_id"]
    state = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert state["guide_id"] == guide_id

    # 2) 触发一次突发事件，产生 v2
    response = client.post(
        f"/api/guides/{guide_id}/incident",
        json={
            "action": {
                "action_id": "act_history",
                "action_type": "REPORT_INCIDENT",
                "session_id": session_id,
                "guide_id": guide_id,
                "expected_guide_version": guide["guide_version"],
                "raw_text": "今天下雨了",
            }
        },
    )
    assert response.status_code == 200
    lineage = response.json()["data"]["version_lineage"]
    # 3) 谱系要带攻略版本号，前端才能显示"v2 → v3"
    assert lineage["parent_guide_version"] == guide["guide_version"]
    assert lineage["new_guide_version"] == guide["guide_version"] + 1

    # 4) 历史版本可回查（`?version=` 不能是死参数）
    old = client.get(
        f"/api/guides/{guide_id}", params={"version": guide["guide_version"]}
    )
    assert old.status_code == 200
    assert old.json()["data"]["travel_guide"]["guide_version"] == guide["guide_version"]
    latest = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    assert latest["guide_version"] == guide["guide_version"] + 1
