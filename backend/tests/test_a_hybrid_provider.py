"""A 线「高德实时路线 + 其余 Mock」混合 Provider 行为测试。

这些用例只验证公开行为，并且**全部使用可注入的假 transport，不访问网络**，
也不读取或输出任何真实 Key。覆盖：

1. 步行响应 → 共享 `RouteOption`；
2. 公交/地铁响应 → 费用、步行、换乘、`METRO`/`BUS` 判定；
3. 高德业务错误 / 空结果 / 网络错误 → 回落 Mock，`source` 仍为 `MOCK`；
4. Key 缺失时不发 HTTP 请求并回落；旧名 `MAP_API_KEY` 仍兼容；
5. 相同请求命中进程内缓存；
6. `build_mcp_provider` 的 `MOCK` / `HYBRID` 行为与其余 8 个工具的委托；
7. `api/deps.py` 通过 factory 装配。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.providers.amap_route import (
    TRANSIT_ENDPOINT,
    WALKING_ENDPOINT,
    AmapRouteClient,
    AmapTransportError,
)
from app.providers.factory import build_mcp_provider
from app.providers.hybrid import HybridMCPProvider
from app.schemas import GetRouteRequest, Money, RouteOption
from app.services.v04_mock_provider import V04MockMCPProvider

_TZ = timezone(timedelta(hours=8))

#: 成都演示目录里很近的两个点（直线约 0.24 km）与较远的两个点（约 1.95 km）
NEAR_ORIGIN, NEAR_DESTINATION = "poi_1003", "rest_2001"
FAR_ORIGIN, FAR_DESTINATION = "poi_1001", "lodging_3004"


class FakeTransport:
    """记录调用并按顺序返回预设 JSON 的假 transport。"""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def get_json(self, url, params, *, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        if isinstance(payload, Exception):
            raise payload
        return payload


def walking_path(duration_seconds: int, distance_meters: int) -> dict:
    return {
        "distance": str(distance_meters),
        "cost": {"duration": str(duration_seconds)},
        "steps": [],
    }


def walking_payload(*paths: dict) -> dict:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "route": {"origin": "", "destination": "", "paths": list(paths)},
    }


def transit_option(
    *,
    duration_seconds: int = 1500,
    distance_meters: int = 9000,
    cost: str = "4.0",
    walking_distance: str = "900",
    metro: bool = True,
) -> dict:
    line_type = "地铁线路" if metro else "公交线路"
    line_name = "地铁1号线(示例)" if metro else "1路(示例)"
    return {
        "cost": {
            "duration": str(duration_seconds),
            "transit_fee": cost,
        },
        "walking_distance": walking_distance,
        "distance": str(distance_meters),
        "nightflag": "0",
        "segments": [
            {
                "walking": {
                    "distance": "300",
                    "cost": {"duration": "240"},
                },
                "bus": {"buslines": [{"name": line_name, "type": line_type}]},
            },
            {
                "walking": {
                    "distance": "600",
                    "cost": {"duration": "480"},
                },
                "bus": {"buslines": [{"name": "2路(示例)", "type": "公交线路"}]},
            },
        ],
    }


def transit_payload(*transits: dict) -> dict:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "route": {
            "origin": "",
            "destination": "",
            "distance": "9000",
            "transits": list(transits),
        },
    }


def build_hybrid(transport, *, api_key: str = "unit-test-key") -> HybridMCPProvider:
    return HybridMCPProvider(
        mock=V04MockMCPProvider(),
        route_client=AmapRouteClient(api_key=api_key, transport=transport),
    )


# --- 1. 步行转换 -------------------------------------------------------------


def test_walking_response_maps_to_shared_route_option() -> None:
    transport = FakeTransport(
        walking_payload(
            walking_path(1200, 1600),  # 较慢，排序后应排在后面
            walking_path(600, 800),
        )
    )
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)

    response = client.get_route(
        GetRouteRequest(
            origin=NEAR_ORIGIN,
            destination=NEAR_DESTINATION,
            allowed_modes=["WALK"],
        )
    )

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == WALKING_ENDPOINT
    assert call["params"]["key"] == "unit-test-key"
    # 发给高德的是「经度,纬度」，绝不是资源 ID
    assert call["params"]["origin"] == "104.055000,30.646000"
    assert call["params"]["destination"] == "104.056000,30.648000"
    assert call["params"]["show_fields"] == "cost"
    assert NEAR_ORIGIN not in call["params"]["origin"]

    assert response is not None
    assert len(response.routes) == 2
    route = response.routes[0]
    assert isinstance(route, RouteOption)
    assert route.mode == "WALK"
    assert route.duration_minutes == 10  # 600s 更快，确定性排序后排在第一条
    assert route.distance_km == 0.8
    assert route.estimated_cost == Money(amount=0, currency="CNY")
    assert route.walking_minutes == 10
    assert route.transfer_count == 0
    assert route.source == "PLATFORM"
    assert route.is_estimated is True


# --- 2. 公交 / 地铁转换 ------------------------------------------------------


def test_transit_metro_response_maps_cost_walking_and_transfers() -> None:
    depart_at = datetime(2026, 10, 3, 9, 30, tzinfo=_TZ)
    transport = FakeTransport(transit_payload(transit_option(metro=True)))
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)

    response = client.get_route(
        GetRouteRequest(
            origin=FAR_ORIGIN,
            destination=FAR_DESTINATION,
            depart_at=depart_at,
        )
    )

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == TRANSIT_ENDPOINT
    # 公交请求必须带成都城市参数；depart_at 必须转成日期与时间
    assert call["params"]["city1"] == "028"
    assert call["params"]["city2"] == "028"
    assert call["params"]["show_fields"] == "cost"
    assert call["params"]["date"] == "2026-10-03"
    assert call["params"]["time"] == "09-30"

    assert response is not None
    route = response.routes[0]
    assert route.mode == "METRO"  # 方案里出现地铁线路
    assert route.duration_minutes == 25
    assert route.distance_km == 9.0
    assert route.estimated_cost == Money(amount=4.0, currency="CNY")
    assert route.walking_minutes == 12  # 240s + 480s
    assert route.transfer_count == 1
    assert route.source == "PLATFORM"
    assert route.congestion_level is None


def test_transit_without_metro_maps_to_bus() -> None:
    transport = FakeTransport(transit_payload(transit_option(metro=False)))
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)

    response = client.get_route(
        GetRouteRequest(origin=FAR_ORIGIN, destination=FAR_DESTINATION)
    )

    assert response is not None
    assert response.routes[0].mode == "BUS"


def test_unsupported_allowed_mode_skips_live_http() -> None:
    transport = FakeTransport(transit_payload(transit_option(metro=True)))
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)

    response = client.get_route(
        GetRouteRequest(
            origin=FAR_ORIGIN,
            destination=FAR_DESTINATION,
            allowed_modes=["TAXI"],
        )
    )

    assert response is None
    assert transport.calls == []


# --- 3. 失败回落 -------------------------------------------------------------


def test_amap_business_error_falls_back_to_mock() -> None:
    request = GetRouteRequest(origin="poi_1001", destination="poi_1003")
    transport = FakeTransport(
        {"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001"}
    )
    hybrid = build_hybrid(transport)

    response = hybrid.get_route(request)
    fallback = V04MockMCPProvider().get_route(request)

    assert response == fallback
    assert len(transport.calls) == 1  # 确实试过高德，但被业务错误拒绝
    assert response.routes
    assert response.routes[0].source == "MOCK"
    assert response.routes[0].is_estimated is True
    assert hybrid.last_route_source == "MOCK"


def test_amap_empty_result_falls_back_to_mock() -> None:
    request = GetRouteRequest(origin="poi_1001", destination="poi_1003")
    transport = FakeTransport(walking_payload())  # status=1，但没有任何 paths
    hybrid = build_hybrid(transport)

    response = hybrid.get_route(request)

    assert response.routes
    assert response.routes[0].source == "MOCK"
    assert hybrid.last_route_source == "MOCK"


def test_transport_error_falls_back_to_mock() -> None:
    request = GetRouteRequest(origin="poi_1001", destination="poi_1003")
    hybrid = build_hybrid(FakeTransport(AmapTransportError("read timeout")))

    response = hybrid.get_route(request)

    assert response.routes
    assert response.routes[0].source == "MOCK"


def test_unresolvable_resource_id_is_not_sent_as_coordinate() -> None:
    transport = FakeTransport(walking_payload(walking_path(600, 800)))
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)

    response = client.get_route(
        GetRouteRequest(origin="poi_does_not_exist", destination=NEAR_DESTINATION)
    )

    assert response is None
    assert transport.calls == []


# --- 4. Key 缺失与旧名兼容 ----------------------------------------------------


def test_missing_key_skips_http_and_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("MAP_API_KEY", raising=False)
    transport = FakeTransport(walking_payload(walking_path(600, 800)))
    hybrid = HybridMCPProvider(
        mock=V04MockMCPProvider(),
        route_client=AmapRouteClient(transport=transport),
    )

    response = hybrid.get_route(
        GetRouteRequest(origin=NEAR_ORIGIN, destination=NEAR_DESTINATION)
    )

    assert transport.calls == []  # 没有 Key 时一次 HTTP 都不能发
    assert response.routes
    assert response.routes[0].source == "MOCK"


def test_env_keys_are_supported_without_hardcoding(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.setenv("MAP_API_KEY", "legacy-key")
    legacy_transport = FakeTransport(walking_payload(walking_path(600, 800)))
    AmapRouteClient(transport=legacy_transport).get_route(
        GetRouteRequest(origin=NEAR_ORIGIN, destination=NEAR_DESTINATION)
    )
    assert legacy_transport.calls[0]["params"]["key"] == "legacy-key"

    monkeypatch.setenv("AMAP_API_KEY", "preferred-key")
    preferred_transport = FakeTransport(walking_payload(walking_path(600, 800)))
    AmapRouteClient(transport=preferred_transport).get_route(
        GetRouteRequest(origin=NEAR_ORIGIN, destination=NEAR_DESTINATION)
    )
    assert preferred_transport.calls[0]["params"]["key"] == "preferred-key"


# --- 5. 进程内缓存 -----------------------------------------------------------


def test_same_request_hits_process_cache() -> None:
    transport = FakeTransport(walking_payload(walking_path(600, 800)))
    client = AmapRouteClient(api_key="unit-test-key", transport=transport)
    request = GetRouteRequest(
        origin=NEAR_ORIGIN, destination=NEAR_DESTINATION, allowed_modes=["WALK"]
    )

    first = client.get_route(request)
    second = client.get_route(request)

    assert first == second
    assert len(transport.calls) == 1


def test_hybrid_reuses_cache_between_planning_and_guide() -> None:
    transport = FakeTransport(walking_payload(walking_path(600, 800)))
    hybrid = build_hybrid(transport)
    request = GetRouteRequest(
        origin=NEAR_ORIGIN, destination=NEAR_DESTINATION, allowed_modes=["WALK"]
    )

    first = hybrid.get_route(request)
    second = hybrid.get_route(request)

    assert first == second
    assert first.routes[0].source == "PLATFORM"
    assert len(transport.calls) == 1


# --- 6. factory 与 8 个工具的委托 --------------------------------------------


class _RecordingMock:
    """记录被委托调用的工具名，不参与真实 Mock 数据构造。"""

    is_mock_only = True

    def __init__(self) -> None:
        self.called: list[str] = []

    def __getattr__(self, name):
        def _call(request):
            self.called.append(name)
            return name

        return _call


def test_factory_builds_mock_and_hybrid(monkeypatch) -> None:
    monkeypatch.delenv("DATA_MODE", raising=False)
    assert isinstance(build_mcp_provider(), V04MockMCPProvider)
    assert isinstance(build_mcp_provider("MOCK"), V04MockMCPProvider)

    transport = FakeTransport(walking_payload(walking_path(600, 800)))
    hybrid = build_mcp_provider("HYBRID", api_key="unit-test-key", transport=transport)
    assert isinstance(hybrid, HybridMCPProvider)
    assert hybrid.is_mock_only is True  # 整体仍是含 Mock 的演示数据

    response = hybrid.get_route(
        GetRouteRequest(
            origin=NEAR_ORIGIN,
            destination=NEAR_DESTINATION,
            allowed_modes=["WALK"],
        )
    )
    assert response.routes[0].source == "PLATFORM"

    with pytest.raises(NotImplementedError):
        build_mcp_provider("SNAPSHOT")


def test_hybrid_delegates_other_eight_tools_to_mock() -> None:
    mock = _RecordingMock()
    hybrid = build_mcp_provider(
        "HYBRID", api_key="", transport=FakeTransport(), mock_provider=mock
    )
    tool_names = [
        "search_planning_ready_destinations",
        "search_travel_knowledge",
        "search_resources",
        "get_resource_facts",
        "get_resource_availability",
        "get_intercity_options",
        "get_weather",
        "get_preparation_rules",
    ]

    for name in tool_names:
        assert getattr(hybrid, name)(object()) == name

    assert mock.called == tool_names


# --- 7. deps 装配 ------------------------------------------------------------


def test_deps_uses_provider_factory(monkeypatch) -> None:
    from app.api import deps

    monkeypatch.setenv("DATA_MODE", "MOCK")
    assert isinstance(deps.build_node_deps().mcp, V04MockMCPProvider)

    monkeypatch.setenv("DATA_MODE", "HYBRID")
    node_deps = deps.build_node_deps()
    assert isinstance(node_deps.mcp, HybridMCPProvider)
    assert node_deps.mcp.is_mock_only is True
