"""端到端联调测试（三条线用同一套数据替身）。

一条链路跑完 P0 的全部关键动作：

```text
建会话 → 追问 → 补齐画像 → 推荐目的地 → 确认 → 排程 → 验证 → 组攻略
      → 确认攻略（锁定节点）→ 突发下雨重规划 → 取新攻略（版本 +1）
```

数据来自 `test_graph_planning` 的假 Provider（A 的 Mock 目前缺住宿/路线/返程城际）。
A 补齐数据后，这个文件里的 `_deps()` 换成 `build_node_deps()` 就是真实端到端。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import build_session_service, get_session_service
from app.main import create_app
from app.services.session_store import InMemorySessionRepository
from test_graph_planning import TRIP_TEXT, _deps


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    service = build_session_service(
        repository=InMemorySessionRepository(), node_deps=_deps()
    )
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)


def test_full_p0_flow_from_message_to_replanned_guide(client: TestClient) -> None:
    session_id = client.post("/api/sessions", json={"run_mode": "DEMO"}).json()["data"][
        "session_id"
    ]

    # 1) 信息不全 → 主动追问
    first = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "我想出去玩"}
    ).json()["data"]
    assert first["stage"] == "ASKING_CLARIFICATION"
    assert "还需要确认" in first["assistant_message"]

    # 2) 补齐 → 推荐候选（带证据）
    second = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": TRIP_TEXT}
    ).json()["data"]
    assert second["stage"] == "AWAITING_DESTINATION_CONFIRMATION"
    assert second["destination_candidates"][0]["evidence_ids"]
    assert second["trip_profile"]["duration_days"] == 5

    # 3) 确认 → 排程 → 验证 → 组攻略
    confirmed = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "确认"}
    ).json()["data"]
    assert confirmed["stage"] == "READY"
    guide_id = confirmed["guide_id"]
    assert guide_id, "确认后应当给出攻略"

    guide = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    assert guide["plan_validation_status"] == "VALID"
    assert len(guide["daily_itinerary"]) == 5
    assert guide["lodging"]["stay_segments"][0]["lodging_id"] == "hotel_test_1"
    assert guide["arrival_and_departure"]["return_plan"]["duration_minutes"] > 0

    # 4) 确认攻略 → 锁定一个节点，版本 +1
    locked_node = guide["daily_itinerary"][0]["nodes"][0]["node_id"]
    confirmed_guide = client.post(
        f"/api/guides/{guide_id}/confirm",
        json={
            "expected_guide_version": guide["guide_version"],
            "lock_node_ids": [locked_node],
            "idempotency_key": "e2e-confirm",
        },
    ).json()["data"]["travel_guide"]
    assert confirmed_guide["lifecycle_status"] == "CONFIRMED"
    assert confirmed_guide["guide_version"] == guide["guide_version"] + 1
    # 锁定节点在后续重规划里必须原样保留（§14 不变量 6）
    locked_resource = next(
        node["resource_id"]
        for day in confirmed_guide["daily_itinerary"]
        for node in day["nodes"]
        if node["node_id"] == locked_node
    )

    # 5) 突发下雨 → 只重排当天 → 新攻略版本
    changed = client.post(
        f"/api/guides/{guide_id}/incident",
        json={
            "action": {
                "action_id": "act_rain",
                "action_type": "REPORT_INCIDENT",
                "session_id": session_id,
                "guide_id": guide_id,
                "expected_guide_version": confirmed_guide["guide_version"],
                "raw_text": "今天下雨了",
            }
        },
    )
    assert changed.status_code == 200
    data = changed.json()["data"]
    assert data["travel_guide"]["guide_version"] == confirmed_guide["guide_version"] + 1
    assert data["version_lineage"]["replacement_relations"], "必须记录替换关系"
    assert locked_resource in {
        node["resource_id"]
        for day in data["travel_guide"]["daily_itinerary"]
        for node in day["nodes"]
    }, "锁定节点不得被重规划改掉"

    # 6) 新版本可回取
    latest = client.get(f"/api/guides/{guide_id}").json()["data"]["travel_guide"]
    assert latest["guide_version"] == data["travel_guide"]["guide_version"]
    old = client.get(
        f"/api/guides/{guide_id}", params={"version": guide["guide_version"]}
    )
    assert old.status_code == 404, "旧版本被新版本替换后不应再命中"


def test_real_provider_reports_missing_lodging_instead_of_failing(
    client: TestClient,
) -> None:
    """真实 Mock 数据（没有住宿）下的行为：明确报缺，不崩、不伪造。"""

    app = create_app()
    service = build_session_service(repository=InMemorySessionRepository())
    app.dependency_overrides[get_session_service] = lambda: service
    real = TestClient(app)
    session_id = real.post("/api/sessions", json={"run_mode": "DEMO"}).json()["data"][
        "session_id"
    ]
    real.post(f"/api/sessions/{session_id}/messages", json={"text": TRIP_TEXT})
    body = real.post(
        f"/api/sessions/{session_id}/messages", json={"text": "确认"}
    ).json()["data"]
    assert body["stage"] == "INSUFFICIENT_DATA"
    assert body["guide_id"] is None
    assert any("住宿" in item for item in body["degraded_items"])
