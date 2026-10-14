# ADR-001: 块编辑采用「按操作分档」重算，而非全量重算

## Status: Accepted (2026-10-12)

## Background

计划书块级编辑需要回答一个核心问题：改一个块之后，日程怎么重算？

约束来自 `app/planning/daily_schedule.py:719`：
```python
self.time += self.duration + self.meal_minutes
```
时间是**天内链式累加**的。同时 `DailySchedule.setup()`（`daily_schedule.py:89`）让每天从 `day_start` 重新起算——**天与天之间时间链独立**。

一次完整规划的成本：`plan_inputs.create()`（LLM）+ `plan_review.review()`（LLM）+ `plan_routes.prepare_routes()`（全量路线查询 N pair × 3 modes）。实测推导 60–180s。

## Decision

**不二选一，按操作类型分档。** 判据只有一条：

> 该操作是否改变「某一天的景点有序集合」？

| 档 | 判据 | 机制 | 外部调用 | 延迟 |
|---|---|---|---|---|
| **C 时间链重算** | 否 | 新写 `rechain()` 纯函数，级联平移 | 无 | <1s |
| **D preview 重算** | 是 | 写 `visit_analysis` → `_generate(preview=True)` → evidence 回填 → 合并 | 路线查询 | 1–3s |
| **不提供** | 涉及新增未采集地点 | 路由到现有 `search_spots` → `select` → `plan` | 全量 | 60–180s |

MVP 内：`edit_block` / `add_block` = C 档；`remove_block`(spot) = D 档；`move_block` 降 P2。

关键复用（三条都不需要修改成员三的既有文件）：
1. `app/planning/timeline_tools.prepare()` —— 现成的「块操作 → `visit_analysis`」翻译与校验层，已有 `tests/test_timeline_tools.py`
2. `app/planning/engine._generate(preview=True)` —— 现成的**零 LLM** 重算通道（`propose()` 走 `provisional()` 纯计算，`plan_review` 给 `not_run`）
3. `app/planning/plan_revision.check()` —— 现成的验收闸门，块编辑与全量修订**共用同一套门禁**

## Consequences

**正面**
- 绝大多数操作零 LLM、零路线查询
- 用户手工修改不会被 LLM 重写覆盖（全量重算会重新推导 `ctx.groups`，这是"真实可用"的头号杀手）
- C 档是纯函数，可单测、可做变异加固
- 对 `app/planning/` 既有文件 **0 行修改**

**负面 / 代价**
- 需要新写 `rechain()` 约 40 行，其口径必须与 `DailySchedule` 保持一致（靠 `plan_revision.check()` 兜底 + 回归测试约束）
- D 档每次触发全量路线查询（见 ADR-003）
- 分档判据需要实现方理解，比"一律全量重算"认知成本高

## Related ADRs
- ADR-002（人工修订记录用 `plan['block_edits']` 新字段）
- ADR-003（路线播种本轮不做）
