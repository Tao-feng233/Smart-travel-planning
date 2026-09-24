"""应用配置。

只从环境变量读取，不在代码里写死任何密钥或平台地址
（见 `MODEL_PROVIDER_AND_SECRETS.md`）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STORE_DIR = Path(".local/plan_store")


@dataclass(frozen=True)
class Settings:
    """运行期配置。

    `plan_store_backend`：
      - `MEMORY`    内存态 + JSON 快照（P0 默认，见进度报告的技术选型）
      - `EPHEMERAL` 纯内存，不落盘（测试用）
    """

    plan_store_backend: str = "MEMORY"
    plan_store_dir: Path = DEFAULT_STORE_DIR

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            plan_store_backend=os.environ.get("PLAN_STORE_BACKEND", "MEMORY").upper(),
            plan_store_dir=Path(os.environ.get("PLAN_STORE_DIR", str(DEFAULT_STORE_DIR))),
        )

    @property
    def persist_snapshots(self) -> bool:
        return self.plan_store_backend == "MEMORY"


settings = Settings.from_env()
