"""共享 Schema（`CONTRACTS.md` **v0.4**）。

本包是三条开发线**唯一**的数据对象定义处：

```text
app.schemas             ← 契约 v0.4（A、B、C 都使用这一层）
app.schemas.v04         ← v0.4 的实现模块（基线与 C 线补齐的对象）
```

⚠️ A、B 只从 `app.schemas` 导入；v0.3 的旧对象（`legacy/`）已在 C1c 中删除，
不要再引用旧名字。

字段、枚举与不变量以根目录 `CONTRACTS.md` 为准。
"""

from .v04 import *  # noqa: F401,F403
from .v04 import MODEL_REGISTRY, MCP_TOOL_MODELS  # noqa: F401
from .v04 import (  # noqa: F401
    Conflict,
    DestinationRecommendation,
    Envelope,
    IncompleteProfileError,
    PlanState,
    RepairOption,
    ResourceCandidateBase,
    ResourceCandidateUnion,
    TripProfile,
    TripProfileDraft,
    UserAction,
    VersionLineage,
    finalize_trip_profile,
    parse_resource_candidate,
)

__all__ = [
    name
    for name in dir()
    if not name.startswith("_") and name not in {"v04"}
]
