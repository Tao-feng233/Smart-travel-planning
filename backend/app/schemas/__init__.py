"""共享 Schema（`CONTRACTS.md` **v0.4**）。

本包是三条开发线**唯一**的数据对象定义处：

```text
app.schemas             ← 契约 v0.4（A、B 使用这一层）
app.schemas.v04         ← v0.4 的实现模块（基线与 C1 补齐的对象）
app.schemas.legacy      ← v0.3 旧对象，仅 C 线内部代码在迁移完成前使用
```

⚠️ A、B 只从 `app.schemas` 导入；`legacy` 是迁移过渡产物，**不要引用**，
它会在 C1c 完成后删除。

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
    if not name.startswith("_") and name not in {"legacy", "v04"}
]
