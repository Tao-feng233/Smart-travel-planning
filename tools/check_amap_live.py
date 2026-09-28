"""受控验证高德实时路线，不打印密钥或第三方原始响应。

从仓库根目录运行：

    python tools/check_amap_live.py

要求进程环境中已有 ``AMAP_API_KEY``。脚本固定发出一条成都步行请求和
一条成都公交/地铁请求，只输出规范化后的共享 ``RouteOption`` 摘要。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.providers.amap_route import AmapRouteClient  # noqa: E402
from app.schemas import GetRouteRequest  # noqa: E402


def _safe_summary(client: AmapRouteClient, request: GetRouteRequest) -> dict:
    response = client.get_route(request)
    if response is None or not response.routes:
        return {
            "origin": request.origin,
            "destination": request.destination,
            "ok": False,
            "error": client.last_error,
        }
    route = response.routes[0]
    return {
        "origin": request.origin,
        "destination": request.destination,
        "ok": True,
        "route": route.model_dump(mode="json"),
    }


def main() -> int:
    client = AmapRouteClient()
    requests = [
        GetRouteRequest(
            origin="poi_1003",
            destination="rest_2001",
            allowed_modes=["WALK"],
        ),
        GetRouteRequest(
            origin="poi_1001",
            destination="lodging_3004",
            depart_at=datetime(
                2026, 10, 3, 9, 30, tzinfo=timezone(timedelta(hours=8))
            ),
            allowed_modes=["METRO", "BUS"],
        ),
    ]
    results = [_safe_summary(client, request) for request in requests]
    print(json.dumps({"provider": "AMAP", "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
