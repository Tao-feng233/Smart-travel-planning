"""FastAPI 依赖注入。

所有可替换的实现都在这里装配：

* `TripProfileParser`     → 现在 `StubTripProfileParser`，B2 完成后替换
* `DestinationRecommender` → 现在 `StubDestinationRecommender`，B4 完成后替换
* `TravelMCPClient`       → 现在 `FakeTravelMCPClient`，A4 完成后替换
* `SessionRepository`     → 现在内存 + JSON 快照，P1 可换成 MySQL
"""

from __future__ import annotations

from app.core import settings
from app.graph import NodeDeps, build_graph
from app.services.destination_recommender import StubDestinationRecommender
from app.services.fake_data import DESTINATIONS
from app.services.request_parser import StubTripProfileParser
from app.services.session_service import SessionService
from app.services.session_store import InMemorySessionRepository
from app.services.travel_mcp_client import FakeTravelMCPClient


def known_destinations() -> dict[str, str]:
    """“目的地名称 → ID”映射。

    现阶段来自 C 线的模拟数据；A 线接入后应改为从
    `search_planning_ready_destinations` 的别名索引获取。
    """

    return {item["name"]: item["destination_id"] for item in DESTINATIONS}


def build_repository() -> InMemorySessionRepository:
    snapshot_dir = settings.plan_store_dir if settings.persist_snapshots else None
    return InMemorySessionRepository(snapshot_dir=snapshot_dir)


def build_node_deps() -> NodeDeps:
    return NodeDeps(
        parser=StubTripProfileParser(),
        mcp=FakeTravelMCPClient(),
        recommender=StubDestinationRecommender(),
        known_destinations=known_destinations(),
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
