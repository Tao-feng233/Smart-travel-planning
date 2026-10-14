# ADR-002: 人工修订记录用 `plan['block_edits']` 新字段，不扩展 `stale`

## Status: Accepted (2026-10-12)

## Background

块级编辑操作的是 **plan 事件层**；`app/agents/edit_tools.py` 的既有编辑工具操作的是 **workspace 选择层**。两层并存产生一个必须回答的问题：用户在 plan 层逐块改完之后，下一次 `generate_plan` 会不会把这些手工修改冲掉？

如果会，块级编辑就是伪功能。

现有 `plan['stale']` 语义 = 上游选择变了，计划已过期。需要新增"计划内有用户手工痕迹"这一维度。

## Decision

**新增 `plan['block_edits']` 字段，绝不扩展 `stale`。**

命名由 team-lead 裁定：项目里 `revision` 已是 workspace 版本号语义（`storage.py:259`），再引入 `revisions` 必然混淆，故用 `block_edits`。

**为什么不扩展 `stale`**
1. `stale` 是布尔量，有 **10 处写入方**（`workspaces.py:14`、`timeline_tools.py:215,261`、`visit_analysis.py:595`、`foods.py:766,795`、`locations.py:241`、`requirements.py:12`、`visits.py:54`、`auto_selection.py:406`）+ **1 处硬门禁**（`workspaces.py:225` 导出时 `if stale: raise 409`）。扩成复合语义等于要求这 11 处读者全部正确区分——沉默逻辑错误的教科书场景。
2. 两者**正交**：`stale` = 计划与上游选择的一致性；`block_edits` = 计划内部的用户手工痕迹。**可以同真**——用户改了 3 个块之后又改了景点选择，布尔量表达不了。

**数据结构要点**
- **回放定位主键是 `candidate_id`，不是 `block_id`**。重算后 event 是新对象，`block_id` 会变；`candidate_id` 不变。这是回放能命中的唯一保证。
- `after` **只存用户真正拥有的值**（`duration` / `note` / `name`）。`start`/`end` 是派生值，禁止存入——存了会与级联结果打架。
- `replayable`：`spot` = `true`；`rest` / `free` / `add_free` = `false`（无 `candidate_id`，重算后无法稳定定位，靠 `(date, kind, 序号)` 会删错块）。
- `superseded`：被覆盖或"全部重新生成"时置 `true`，**不清空**（保留审计与 `before` 快照，`before` 同时是撤销依据）。
- `source` 固定 `"user_explicit"`，复用 `app/core/contracts.py:248` 的 `SOURCE_USER` 词表，不新造。

**「保留我的修改」的实现**（不需要改 `visit_analysis`）：
```
1. plan = await _generate(w, progress)                          # 全量，零侵入
2. plan = block_edits.replay(plan, w["plan"]["block_edits"])    # 按 candidate_id 写回
3. block_edits.rechain(plan, affected_dates)                    # 复用 ADR-001 的 C 档引擎
4. plan_revision.check(w, plan)                                 # 现有验收闸门
5. 保留 block_edits
```
第 3 步复用的就是删除/改时长要用的同一套引擎，因此 F3 的边际成本只有 `replay()` 约 30 行 + 一个确认闸门。

## Consequences

**正面**
- 手工修改在重算后可保留，"局部不满意不必赌上整份计划书"成立
- 复用 C 档引擎，边际成本低
- 正交字段，不污染 `stale` 的 11 处读者

**负面 / 代价**
- 回放后**可能产出一份自相矛盾的计划书**（用户把 A 设成 150 分钟，B 被挤到 22:00）
- 因此架构裁定：**AC-4.3 拆成 a/b**——回放后有阻断级冲突时，不得静默写入，必须回用户逐项确认
- `rest` / `free` 的编辑在重算后不保留，UI 必须明说（而非假装保留）

## Related ADRs
- ADR-001（分档重算，提供 `rechain` 引擎）
- ADR-003（路线播种本轮不做）
