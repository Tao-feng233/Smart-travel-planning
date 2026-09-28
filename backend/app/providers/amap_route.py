"""高德（AMap）Web 服务路线 Provider。

这里只覆盖九个 MCP 工具中的 `get_route`：把共享 `GetRouteRequest` 转成高德
官方 Web 服务请求，再把响应规范化成共享 `GetRouteResponse` / `RouteOption`。

设计边界（对齐任务书与 `docs/DATA_PROVIDER_ARCHITECTURE.md`）：

* Key 只从环境变量 `AMAP_API_KEY` 读取（兼容旧名 `MAP_API_KEY`），绝不硬编码；
* Provider 收到的是资源 ID，必须先经当前成都 Mock 资源目录解析成经纬度，
  解析失败时**不会**把资源 ID 当坐标发给高德；
* 短距离优先「步行路径规划 2.0」``/v5/direction/walking``，
  较远距离优先「公交路径规划 2.0」``/v5/direction/transit/integrated``（可含地铁）；
* 任何不确定情况（缺 Key、无法解析坐标、网络或业务错误、空结果）一律返回
  `None`，由上层 `HybridMCPProvider` 回退到 Mock；本模块**从不**把回退结果
  标成高德真实数据；
* HTTP 走可注入的 transport，单元测试不访问网络；
* 成功结果进入进程内缓存，避免规划与攻略阶段对完全相同的路线重复请求。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any, Protocol

from app.schemas import GetRouteRequest, GetRouteResponse, Money, RouteOption
from app.services.v04_mock_provider import route_coordinate

logger = logging.getLogger(__name__)

WALKING_ENDPOINT = "https://restapi.amap.com/v5/direction/walking"
TRANSIT_ENDPOINT = "https://restapi.amap.com/v5/direction/transit/integrated"

DEFAULT_TIMEOUT_SECONDS = 5.0
#: 直线距离不超过该值时优先步行，超过则走公交综合规划（可含地铁）
WALK_MAX_STRAIGHT_KM = 1.5
#: 仅用于把高德的 `walking_distance`（米）换算成分钟
WALK_SPEED_KMH = 4.5
#: 高德 v5 公交接口只接受 citycode；成都区号 / citycode 为 028。
TRANSIT_CITY_CODE = "028"
#: 共享 `SourceType` 允许的真实来源值
SOURCE_PLATFORM = "PLATFORM"

_PUBLIC_TRANSIT_MODES = {"BUS", "METRO"}


class AmapTransportError(RuntimeError):
    """高德 HTTP / 网络层错误（超时、连接失败、非 200、非法 JSON）。"""


class AmapTransport(Protocol):
    """可注入的 HTTP transport；单元测试用假实现，禁止访问网络。"""

    def get_json(
        self, url: str, params: Mapping[str, str], *, timeout: float
    ) -> Mapping[str, Any]: ...


class HttpxAmapTransport:
    """默认 transport：复用项目已有 `httpx`，不引入新依赖。"""

    def get_json(
        self, url: str, params: Mapping[str, str], *, timeout: float
    ) -> Mapping[str, Any]:
        import httpx

        try:
            response = httpx.get(url, params=dict(params), timeout=timeout)
        except httpx.HTTPError as exc:  # 超时 / 连接失败
            raise AmapTransportError(str(exc)) from exc
        if response.status_code != 200:
            raise AmapTransportError(f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AmapTransportError("高德响应不是合法 JSON") from exc
        if not isinstance(payload, Mapping):
            raise AmapTransportError("高德响应 JSON 顶层不是对象")
        return payload


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timeout_from_env() -> float:
    """读取可选的 `AMAP_TIMEOUT_SECONDS`，非法/缺省时用默认值。"""

    value = _to_float(os.getenv("AMAP_TIMEOUT_SECONDS"))
    return value if value and value > 0 else DEFAULT_TIMEOUT_SECONDS


def _format_coordinate(coordinate: tuple[float, float]) -> str:
    """高德要求「经度在前，纬度在后」，逗号分隔。"""

    latitude, longitude = coordinate
    return f"{longitude:.6f},{latitude:.6f}"


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    latitude_1, longitude_1 = radians(a[0]), radians(a[1])
    latitude_2, longitude_2 = radians(b[0]), radians(b[1])
    delta_latitude = latitude_2 - latitude_1
    delta_longitude = longitude_2 - longitude_1
    h = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(delta_longitude / 2) ** 2
    )
    return 2 * 6371.0 * asin(sqrt(h))


def _route_sort_key(route: RouteOption) -> tuple:
    """确定性排序：耗时最短的第一条即规划器可直接执行的主方案。"""

    return (
        route.duration_minutes,
        route.distance_km if route.distance_km is not None else float("inf"),
        route.mode,
        route.walking_minutes if route.walking_minutes is not None else 0,
    )


def _count_rides(segments: list) -> tuple[int, bool]:
    """统计公交乘坐次数并判断方案里是否含地铁。"""

    rides = 0
    has_metro = False
    for segment in segments:
        bus = segment.get("bus") or {}
        for line in bus.get("buslines") or []:
            rides += 1
            label = " ".join(
                str(line.get(field) or "") for field in ("type", "name")
            )
            if "地铁" in label:
                has_metro = True
    return rides, has_metro


def _transit_walking_minutes(transit: Mapping[str, Any], segments: list) -> int:
    """优先用各步行段的实际耗时求和，拿不到再按 `walking_distance` 估算。"""

    seconds = 0.0
    for segment in segments:
        walking = segment.get("walking") or {}
        walking_cost = walking.get("cost") or {}
        seconds += (
            _to_float(walking_cost.get("duration"))
            or _to_float(walking.get("duration"))
            or 0.0
        )
    if seconds > 0:
        return max(1, round(seconds / 60))
    distance_meters = _to_float(transit.get("walking_distance"))
    if distance_meters and distance_meters > 0:
        return max(1, round(distance_meters / 1000 / WALK_SPEED_KMH * 60))
    return 0


class AmapRouteClient:
    """高德 Web 服务路线客户端；失败一律返回 `None`，由调用方决定回退。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: AmapTransport | None = None,
        timeout: float | None = None,
        coordinate_resolver=None,
    ) -> None:
        #: 显式传入优先（含空串 = 明确禁用）；`None` 表示按请求读取环境变量
        self._api_key = api_key
        self._transport = transport if transport is not None else HttpxAmapTransport()
        self._timeout = timeout if timeout is not None else _timeout_from_env()
        self._resolve = coordinate_resolver or route_coordinate
        self._cache: dict[tuple, GetRouteResponse] = {}
        #: 最近一次失败原因（不含 Key，便于降级说明与测试观察）
        self.last_error: str | None = None

    @property
    def api_key(self) -> str:
        if self._api_key is not None:
            return str(self._api_key).strip()
        return (
            os.getenv("AMAP_API_KEY") or os.getenv("MAP_API_KEY") or ""
        ).strip()

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _cache_key(request: GetRouteRequest) -> tuple:
        return (
            request.origin,
            request.destination,
            request.depart_at.isoformat() if request.depart_at else None,
            tuple(request.allowed_modes),
        )

    def get_route(self, request: GetRouteRequest) -> GetRouteResponse | None:
        key = self._cache_key(request)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._query(request)
        # 只缓存成功的高德结果：失败/回退不缓存，便于后续请求重试实时数据
        if result is not None:
            self._cache[key] = result
        return result

    # --- 内部实现 -----------------------------------------------------------

    def _fetch(
        self, url: str, params: Mapping[str, str]
    ) -> Mapping[str, Any]:
        return self._transport.get_json(url, params, timeout=self._timeout)

    @staticmethod
    def _prefers_walking(
        request: GetRouteRequest,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> bool | None:
        allowed = set(request.allowed_modes)
        if allowed:
            walk_ok = "WALK" in allowed
            transit_ok = bool(allowed & _PUBLIC_TRANSIT_MODES)
            if not walk_ok and not transit_ok:
                return None
            if walk_ok and not transit_ok:
                return True
            if transit_ok and not walk_ok:
                return False
        return _haversine_km(origin, destination) <= WALK_MAX_STRAIGHT_KM

    @staticmethod
    def _transit_params(
        api_key: str,
        origin: tuple[float, float],
        destination: tuple[float, float],
        depart_at: datetime | None,
    ) -> dict[str, str]:
        params = {
            "key": api_key,
            "origin": _format_coordinate(origin),
            "destination": _format_coordinate(destination),
            "city1": TRANSIT_CITY_CODE,
            "city2": TRANSIT_CITY_CODE,
            "strategy": "0",
            "show_fields": "cost",
        }
        if depart_at is not None:
            params["date"] = depart_at.strftime("%Y-%m-%d")
            params["time"] = depart_at.strftime("%H-%M")
        return params

    @staticmethod
    def _payload_error(payload: Mapping[str, Any]) -> str | None:
        if str(payload.get("status")) != "1":
            info = payload.get("info") or "UNKNOWN"
            infocode = payload.get("infocode") or ""
            return f"高德业务错误：{info}（infocode={infocode}）"
        return None

    def _query(self, request: GetRouteRequest) -> GetRouteResponse | None:
        api_key = self.api_key
        if not api_key:
            self.last_error = "未配置 AMAP_API_KEY / MAP_API_KEY，跳过实时路线请求"
            return None

        origin = self._resolve(request.origin)
        destination = self._resolve(request.destination)
        if origin is None or destination is None:
            unresolved = request.origin if origin is None else request.destination
            self.last_error = (
                f"资源 {unresolved!r} 不在当前 Mock 资源目录中，"
                "未把资源 ID 当坐标发送"
            )
            return None

        try:
            prefers_walking = self._prefers_walking(request, origin, destination)
            if prefers_walking is None:
                self.last_error = "allowed_modes 不包含高德适配器支持的 WALK/BUS/METRO"
                return None
            if prefers_walking:
                payload = self._fetch(
                    WALKING_ENDPOINT,
                    {
                        "key": api_key,
                        "origin": _format_coordinate(origin),
                        "destination": _format_coordinate(destination),
                        "show_fields": "cost",
                    },
                )
                routes = self._normalize_walking(payload)
            else:
                payload = self._fetch(
                    TRANSIT_ENDPOINT,
                    self._transit_params(
                        api_key, origin, destination, request.depart_at
                    ),
                )
                routes = self._normalize_transit(payload)
        except AmapTransportError as exc:
            self.last_error = f"高德请求失败：{exc}"
            return None

        if not routes:
            self.last_error = (
                self._payload_error(payload) or "高德未返回可用路线"
            )
            return None

        routes.sort(key=_route_sort_key)
        self.last_error = None
        return GetRouteResponse(routes=routes)

    @staticmethod
    def _normalize_walking(
        payload: Mapping[str, Any],
    ) -> list[RouteOption]:
        if str(payload.get("status")) != "1":
            return []
        route = payload.get("route") or {}
        options: list[RouteOption] = []
        for path in route.get("paths") or []:
            cost = path.get("cost") or {}
            duration_seconds = (
                _to_float(cost.get("duration"))
                or _to_float(path.get("duration"))
            )
            if not duration_seconds or duration_seconds <= 0:
                continue
            minutes = max(1, round(duration_seconds / 60))
            distance_meters = _to_float(path.get("distance"))
            options.append(
                RouteOption(
                    mode="WALK",
                    duration_minutes=minutes,
                    distance_km=(
                        round(distance_meters / 1000, 2)
                        if distance_meters
                        else None
                    ),
                    estimated_cost=Money(amount=0, currency="CNY"),
                    walking_minutes=minutes,
                    transfer_count=0,
                    source=SOURCE_PLATFORM,
                    is_estimated=True,
                )
            )
        return options

    @staticmethod
    def _normalize_transit(
        payload: Mapping[str, Any],
    ) -> list[RouteOption]:
        if str(payload.get("status")) != "1":
            return []
        route = payload.get("route") or {}
        route_distance_meters = _to_float(route.get("distance"))
        options: list[RouteOption] = []
        for transit in route.get("transits") or []:
            cost = transit.get("cost") or {}
            duration_seconds = (
                _to_float(cost.get("duration"))
                or _to_float(transit.get("duration"))
            )
            if not duration_seconds or duration_seconds <= 0:
                continue
            segments = transit.get("segments") or []
            rides, has_metro = _count_rides(segments)
            distance_meters = (
                _to_float(transit.get("distance")) or route_distance_meters
            )
            cost_yuan = (
                _to_float(cost.get("transit_fee"))
                or _to_float(cost.get("fee"))
                or _to_float(transit.get("transit_fee"))
            )
            options.append(
                RouteOption(
                    mode="METRO" if has_metro else "BUS",
                    duration_minutes=max(1, round(duration_seconds / 60)),
                    distance_km=(
                        round(distance_meters / 1000, 2)
                        if distance_meters
                        else None
                    ),
                    estimated_cost=(
                        Money(amount=cost_yuan, currency="CNY")
                        if cost_yuan is not None
                        else None
                    ),
                    walking_minutes=_transit_walking_minutes(transit, segments),
                    transfer_count=max(0, rides - 1),
                    source=SOURCE_PLATFORM,
                    is_estimated=True,
                )
            )
        return options
