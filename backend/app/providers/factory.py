"""Provider factory（`DATA_MODE` 装配入口）。

* `MOCK`   全部使用 `V04MockMCPProvider`（默认，行为不变）；
* `HYBRID` 其余 8 个工具委托 Mock，`get_route` 走高德优先 + Mock 回退
  （见 `app/providers/hybrid.py`）。

`Snapshot` / `Live` 尚未实现，继续显式报 `NotImplementedError`，不静默降级。
业务代码（LangGraph、规划器、REST）只依赖 `MCPProvider` 协议，不感知具体模式。
"""

from __future__ import annotations

import os

from app.providers.amap_route import AmapRouteClient, AmapTransport
from app.providers.base import MCPProvider
from app.providers.hybrid import HybridMCPProvider
from app.services.v04_mock_provider import V04MockMCPProvider


def build_mcp_provider(
    data_mode: str | None = None,
    *,
    api_key: str | None = None,
    transport: AmapTransport | None = None,
    mock_provider: V04MockMCPProvider | None = None,
) -> MCPProvider:
    """按 `DATA_MODE` 装配 Provider；默认仍是 `MOCK`。

    `api_key` / `transport` / `mock_provider` 是测试与替换点，
    生产路径只读环境变量，不在这里写死任何 Key。
    """

    mode = (data_mode or os.getenv("DATA_MODE", "MOCK")).upper()
    if mode == "MOCK":
        return mock_provider if mock_provider is not None else V04MockMCPProvider()
    if mode == "HYBRID":
        mock = mock_provider if mock_provider is not None else V04MockMCPProvider()
        route_client = AmapRouteClient(api_key=api_key, transport=transport)
        return HybridMCPProvider(mock=mock, route_client=route_client)
    raise NotImplementedError(
        f"DATA_MODE={mode} 尚未实现；当前支持 MOCK（默认）与 HYBRID。"
        "Snapshot/Live 将复用同一 MCPProvider 协议。"
    )
