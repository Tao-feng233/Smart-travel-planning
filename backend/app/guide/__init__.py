"""B 线攻略组装层（B6）。

`AGENTS.md`「建议代码边界」把 `backend/app/guide/` 划归 B 线（GuideComposer）。

职责单一：把 C 线规划器产出的内部 `ItineraryPlan` 富化成用户看的七部分
`TravelGuide`。**不规划、不验证、不修复**，那些是 C 线的事；
也不查任何旅游事实，事实一律从数据层素材里取。

用法：

```python
from app.guide import GuideCompositionError, GuideContext, compose_travel_guide

guide = compose_travel_guide(
    plan, profile, context, run_mode=RunMode.DEMO, lifecycle_status="DRAFT"
)
```

`GuideCompositionError` 表示组装素材缺失（例如城际交通还没接入）。
出现它时应当**明确报缺**，不得伪造数据 —— 见 `composer.py` 的说明。
"""

from .composer import (
    NODE_TYPE_LABELS,
    GuideCompositionError,
    GuideContext,
    build_arrival_and_departure,
    build_guide_days,
    build_sources_and_freshness,
    build_trip_summary,
    compose_travel_guide,
    derive_data_assurance_status,
    derive_guide_readiness,
    enrich_node,
)

__all__ = [
    "GuideCompositionError",
    "GuideContext",
    "NODE_TYPE_LABELS",
    "build_arrival_and_departure",
    "build_guide_days",
    "build_sources_and_freshness",
    "build_trip_summary",
    "compose_travel_guide",
    "derive_data_assurance_status",
    "derive_guide_readiness",
    "enrich_node",
]
