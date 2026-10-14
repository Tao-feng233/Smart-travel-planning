# ADR-003: D 档路线播种优化本轮不做

## Status: Accepted (2026-10-12) — 延期，非否决

## Background

ADR-001 的 D 档（删除 spot 块）复用 `_generate(preview=True)`。该路径下 `app/planning/plan_routes.py::prepare_routes` 会执行：

```python
ctx.routes = {} if ctx.preview else dict(await asyncio.gather(...))
```

即 **preview 时 `ctx.routes` 为空**，随后 `route_cache.options()` 会对**每一个** pair 真实查询高德（3 modes × N pair，`asyncio.Semaphore(3)`）。

实际只有被改动的那 1–4 个 pair 需要重查；其余 pair 的测量结果已经保存在当前 plan 的 `event["route"]` 里（含 `minutes` / `distance` / `mode` / `source.queried_at`）。

项目已有供应商限流（`ProviderBudgetRepository`，`app/core/contracts.py:96`），连续操作会消耗高德配额。

## Decision

**本轮不做路线播种。** 接受 D 档每次全量重查，实测延迟 1–3s。

若后续实测超过 8s（或配额告警），再在 `prepare_routes` 末尾追加约 8 行：

```python
# 仅 preview 时：用已存 plan 的测量结果播种，未命中的 pair 才真查
if ctx.preview:
    for d in (ctx.workspace.get("plan") or {}).get("days", []):
        for e in d.get("events", []):
            r = e.get("route") or {}
            if r.get("minutes") is not None and e.get("candidate_id"):
                ctx.routes.setdefault((...prev_id, e["candidate_id"]),
                                      [{**r, "reused": True}])
```

这是**纯追加**，非 preview 路径零影响。播种值必须保留 `source.queried_at` 并标记 `reused`——这是对既有测量结果的复用，不是补造数据。

## Consequences

**正面（本轮）**
- `app/planning/plan_routes.py` **0 行改动**，成员三既有文件零侵入
- 不引入"复用过期测量"的正确性争议
- 省掉一个需要成员三确认的跨模块改动

**负面 / 代价**
- D 档每次触发全量路线查询（N×3），删除操作 1–3s，且消耗高德配额
- 前端需对连续操作做 300ms 防抖（`SPEC` §8.1 坑 #10）
- 性能 NFR 因此**必须按档拆分**：改时长（C 档）p95 < 800ms；删除（D 档）p95 < 3s

**明确不做的事**：不为了把删除压进 800ms 而改用 30 分钟占位。那是用"敢不敢照着走"换一个数字，直接违反项目"不补造数据"铁律。路线查询失败时系统本来就会自动降级成占位（`daily_schedule.py:429-438`），无需我们主动降级。

## 复审触发条件

满足任一即重新评估：
1. 实测 D 档 p95 > 8s
2. 高德配额告警
3. `move_block`（P2）进入排期——它是 D 档且操作频率更高

## Related ADRs
- ADR-001（分档重算，定义 D 档）
- ADR-002（人工修订记录）
