"""Provider factory; only MOCK is implemented in the current A-line stage."""

from __future__ import annotations

import os

from app.providers.base import MCPProvider
from app.services.v04_mock_provider import V04MockMCPProvider


def build_mcp_provider(data_mode: str | None = None) -> MCPProvider:
    mode = (data_mode or os.getenv("DATA_MODE", "MOCK")).upper()
    if mode == "MOCK":
        return V04MockMCPProvider()
    raise NotImplementedError(
        f"DATA_MODE={mode} 尚未实现；当前请使用 MOCK。"
        "Snapshot/Live/Hybrid 将复用同一 MCPProvider 协议。"
    )


