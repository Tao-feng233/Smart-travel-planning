"""把 v0.4 契约模型转成「给模型看的结构化输出说明」。

**不复制任何字段定义**：Schema 一律由 Pydantic 从 `backend/app/schemas/`
现算（`model_json_schema()`）。契约一改，这里自动跟着改，
符合 `AGENTS.md`「共享 Schema 集中放置，不得在三个模块中重复定义」。

提示词里附 Schema 的目的不是让模型「读懂结构」——它当然能懂——
而是把**唯一权威的字段集合**摆到模型面前，减少它自己发明字段的机会。
真正把关的仍然是 `Pydantic` 校验（见 `request_parser.py`）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Type

from pydantic import BaseModel


def schema_text(model: Type[BaseModel], *, exclude: Sequence[str] = ()) -> str:
    """返回紧凑的 JSON Schema 文本，可剔除由系统负责的字段。"""

    schema: dict[str, Any] = model.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name in exclude:
            properties.pop(name, None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [name for name in required if name not in exclude]
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def field_names(model: Type[BaseModel]) -> list[str]:
    return list(model.model_fields)


__all__ = ["schema_text", "field_names"]
