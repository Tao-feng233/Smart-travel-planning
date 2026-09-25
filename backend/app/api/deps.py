"""FastAPI 依赖注入（v0.4 契约）。

所有可替换的实现都在这里装配：

* `TripProfileParser`        → **B2 已替换为 `LLMTripProfileParser`**（LLM 提取，
  未配置模型接口或调用失败时自动降级回 C 线的 `StubTripProfileParser`）
* `DestinationRecommender`   → **B4 已替换为 `LLMDestinationRecommender`**
  （降级口径同 B2，回落到 `StubDestinationRecommender`）
* `MCPProvider`（9 个工具）  → 现在 `V04MockMCPProvider`，A4 完成后替换
* `SessionRepository`        → 现在内存 + JSON 快照，P1 可换成 MySQL

**B 线改动说明**：只改了 `build_node_deps()` 里的两行装配，
没有改动任何契约对象、图节点或服务层代码；两个 STUB 文件原样保留作为降级出口。
模型通道由 `.env` 的 `LLM_PRIMARY_*` 配置，未配置时 `get_llm_provider()`
返回不可用的占位实现，整条链路自动走规则式路径，**行为与替换前完全一致**。
"""

from __future__ import annotations

from app.core import settings
from app.graph import NodeDeps, build_graph
from app.llm import (
    LLMDestinationRecommender,
    LLMTripProfileParser,
    get_llm_provider,
)
from app.services import v04_mock_provider
from app.services.session_service import SessionService
from app.services.session_store import InMemorySessionRepository
from app.services.v04_mock_provider import V04MockMCPProvider


def build_repository() -> InMemorySessionRepository:
    snapshot_dir = settings.plan_store_dir if settings.persist_snapshots else None
    return InMemorySessionRepository(snapshot_dir=snapshot_dir)


def build_node_deps() -> NodeDeps:
    """装配节点依赖（B 线的两个替换点在此接入）。"""

    provider = get_llm_provider()
    return NodeDeps(
        parser=LLMTripProfileParser(provider=provider),
        mcp=V04MockMCPProvider(),
        recommender=LLMDestinationRecommender(provider=provider),
        known_destinations=v04_mock_provider.known_destinations(),
    )


def build_session_service(
    *, repository=None, node_deps: NodeDeps | None = None
) -> SessionService:
    deps = node_deps or build_node_deps()
    mcp = deps.mcp
    return SessionService(
        repository or build_repository(),
        build_graph(deps),
        known_destinations=deps.known_destinations,
        data_is_mock=bool(getattr(mcp, "is_mock_only", False)),
    )


_service: SessionService | None = None


def get_session_service() -> SessionService:
    """FastAPI 依赖：进程内单例。测试可用 `dependency_overrides` 覆盖。"""

    global _service
    if _service is None:
        _service = build_session_service()
    return _service


def reset_session_service() -> None:
    """清空单例（测试用）。"""

    global _service
    _service = None
