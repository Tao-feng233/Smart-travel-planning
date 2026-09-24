"""LangGraph 工作流的阶段名。

`CONTRACTS.md` §11 只给出一个示例值 `VALIDATING`，没有定义完整取值集合
（已登记在 `docs/contract-open-questions.md` 第 1 节）。
本文件是 C 线在实际实现中使用的阶段词汇表，待三人确认后写回契约。

阶段推进顺序（P0）：

```text
CREATED
  → PARSING_REQUEST → CHECKING_FIELDS
      → ASKING_CLARIFICATION（返回用户追问，等待补充）
      → RETRIEVING_DESTINATIONS
          → RECOMMENDING_DESTINATIONS → AWAITING_DESTINATION_CONFIRMATION
          → INSUFFICIENT_DATA（知识库覆盖不足，明确降级）
C3 之后接入：PLANNING → VALIDATING →（REPAIRING）→ READY
```
"""

from enum import Enum


class PlanStage(str, Enum):
    CREATED = "CREATED"
    PARSING_REQUEST = "PARSING_REQUEST"
    CHECKING_FIELDS = "CHECKING_FIELDS"
    ASKING_CLARIFICATION = "ASKING_CLARIFICATION"
    RETRIEVING_DESTINATIONS = "RETRIEVING_DESTINATIONS"
    RECOMMENDING_DESTINATIONS = "RECOMMENDING_DESTINATIONS"
    AWAITING_DESTINATION_CONFIRMATION = "AWAITING_DESTINATION_CONFIRMATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    # 以下阶段在 C3–C6 实现，这里先占位，避免后续改名影响已写好的判断
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    READY = "READY"

    def __str__(self) -> str:  # pragma: no cover - 仅用于可读输出
        return self.value
