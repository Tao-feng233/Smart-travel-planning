"""检查 A 线 Provider 的数据缺口（C4/C7 依赖这些数据）。

用法（在仓库根目录跑）：

```powershell
python tools/check_a_data.py
```

退出码 0 = 必修项都齐了；1 = 还有必修项没到位（C4 的完整行程跑不通）。
每次 A 更新数据后跑一遍即可，不用人工翻代码。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.schemas import (  # noqa: E402
    DateRange,
    GetIntercityOptionsRequest,
    GetRouteRequest,
    GetWeatherRequest,
    SearchResourcesRequest,
)
from app.services.v04_mock_provider import V04MockMCPProvider  # noqa: E402

START = date(2026, 10, 2)
END = date(2026, 10, 6)
DESTINATION = "dest_chengdu"
ORIGIN = "上海"


def main() -> int:
    provider = V04MockMCPProvider()
    range_ = DateRange(start_date=START, end_date=END)
    required: list[tuple[str, bool, str]] = []

    # 1) 住宿候选（必修：ItineraryPlan 的 stay_segments / DayPlan.stay_segment_id 都是必填）
    lodgings = provider.search_resources(
        SearchResourcesRequest(
            resource_type="LODGING", destination_id=DESTINATION, date_range=range_
        )
    ).resources
    areas = provider.search_resources(
        SearchResourcesRequest(
            resource_type="LODGING_AREA", destination_id=DESTINATION, date_range=range_
        )
    ).resources
    required.append(
        (
            "住宿候选 LODGING",
            len(lodgings) > 0,
            f"{len(lodgings)} 个（CONTRACTS §15：P0 要完成住宿区域和人工整理候选）",
        )
    )
    required.append(("住宿区域 LODGING_AREA", len(areas) > 0, f"{len(areas)} 个"))

    # 2) 路线覆盖（必修：P0 要求行程含交通时间；缺数据 C4 只能记 DATA_UNKNOWN）
    places = [
        item.resource_id
        for item in provider.search_resources(
            SearchResourcesRequest(
                resource_type="VISIT_PLACE", destination_id=DESTINATION, date_range=range_
            )
        ).resources
    ]
    restaurants = [
        item.resource_id
        for item in provider.search_resources(
            SearchResourcesRequest(
                resource_type="RESTAURANT", destination_id=DESTINATION, date_range=range_
            )
        ).resources
    ]
    pairs = [(a, b) for a in places for b in [*places, *restaurants] if a != b]
    missing = []
    for origin, target in pairs:
        response = provider.get_route(GetRouteRequest(origin=origin, destination=target))
        if not response.routes:
            missing.append(f"{origin}->{target}")
    required.append(
        (
            "路线覆盖（景点之间双向）",
            not missing,
            f"缺 {len(missing)} 条" + (f"：{', '.join(missing[:4])}…" if missing else ""),
        )
    )

    # 3) 城际交通：去程 + 返程
    outbound = provider.get_intercity_options(
        GetIntercityOptionsRequest(
            origin_city=ORIGIN, destination_id=DESTINATION, arrival_or_departure_date=START
        )
    ).options
    inbound = provider.get_intercity_options(
        GetIntercityOptionsRequest(
            origin_city=DESTINATION, destination_id=ORIGIN, arrival_or_departure_date=END
        )
    ).options
    required.append(("城际交通·去程", len(outbound) > 0, f"{len(outbound)} 条"))
    required.append(("城际交通·返程", len(inbound) > 0, f"{len(inbound)} 条"))

    # 4) 天气覆盖整段行程（B6 的准备提醒要用；缺日会抛 DataMissingError）
    try:
        weather = provider.get_weather(
            GetWeatherRequest(date_range=range_, destination_id=DESTINATION)
        )
        covered = {item.date for item in weather.weather_facts}
        expected = {START}
        cursor = START
        while cursor <= END:
            expected.add(cursor)
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
        required.append(
            (
                "天气覆盖整段行程",
                covered == expected,
                f"{len(weather.weather_facts)}/{len(expected)} 天",
            )
        )
    except Exception as exc:
        required.append(("天气覆盖整段行程", False, f"查询直接失败：{type(exc).__name__}"))

    print("A 线数据到位情况（C4/C7 依赖）")
    print("-" * 46)
    missing_required = 0
    for name, ok, detail in required:
        mark = "OK  " if ok else "缺  "
        print(f"[{mark}] {name:<26} {detail}")
        if not ok:
            missing_required += 1
    print("-" * 46)
    if missing_required:
        print(f"还有 {missing_required} 项必修数据没到位 —— 需要找 A 补（见 PROGRESS_REPORT 缺口清单）。")
        return 1
    print("必修数据都齐了，可以跑完整的 C4 → C5 → C7 链路。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
