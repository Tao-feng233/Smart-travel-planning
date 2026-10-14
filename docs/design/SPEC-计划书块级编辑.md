> 识途 TravelSense · 技术规格（自包含契约）
> 作者：高见远（首席架构师） | 版本：v1.0 | 状态：待评审
> 上游：`docs/design/PRD-计划书块级编辑.md`（许清楚）· `docs/design/DESIGN.md`（颜好看）
> 优先级锚点：**真实可用**（端到端跑通 + 测试覆盖）

---

## 0. 范围锚定

### 0.1 版本锚定（按实际安装版本写，禁止凭印象）

| 项 | 版本/事实 | 证据 |
|---|---|---|
| Python | 3.13（venv `D:\ShiTu\.venv`） | 项目根目录 |
| Web 框架 | FastAPI（Pydantic v2 风格 `BaseModel` + `Field`） | `app/api/workspaces.py:6-7` |
| 前端 | 原生 ES5/ES6，**无构建步骤**，脚本由 `index.html` 顺序加载 | `frontend/index.html:552-564` |
| 静态资源 | `/assets/**`，由 `app/api/page_assets.py` 解析 `index.html` 算 sha256[:12] | `app/api/page_assets.py` |
| 数据库 | SQLite + WAL，workspace 整体 JSON 快照 | `app/persistence/storage.py:78` |
| LLM | DeepSeek（默认 `deepseek-flash`） | 项目配置 |
| 向量库 | Qdrant 本地持久化 | 项目配置 |
| 图标 | **Lucide（ISC）24×24 / stroke 2 / round cap-join**，以 `frontend/core/icons.js` path 常量表 + `icon()` 单一出口交付 | Spec §7.2 |
| 时间工具 | `app/planning/time_values.py` 的 `minute()` / `clock()` / `round_up()` | 见坑 #12 |

### 0.2 本次做什么（MVP）

| 功能 | action | 档 | 回放 |
|---|---|---|---|
| 改 spot 停留时长 / 备注 | `edit_block` | C（纯时间链，<1s） | 应 `replayable:true` |
| 改 rest / free 时长或备注 | `edit_block` | C | 禁 `replayable:false` |
| 删除 spot 块 | `remove_block` | D（真查 1 条新路线，1–3s） | 应 由 `selected_spots` 天然保留 |
| 新增自定义块（`kind:"free"`） | `add_block` | C | 禁 `replayable:false` |
| 展开已关联官方攻略 | **纯前端**，无 action | — | — |
| 撤销 | 现有 `undo` | — | 服务端快照 |

### 0.3 本次明确不做（out-of-scope，杜绝镀金）

1. `move_block`（同日调序 / 跨日移动）→ **P2**。D 档，3–15s + 全量路线查询 + 耗配额，成本远高于收益。
2. `block_evidence`（手动关联/取消关联攻略）→ 不做。需求是"展开**已关联**的攻略"。
3. 导出 Markdown 带攻略正文 → 不做。`report.py:197-200` 一行链接的行为保持不变（用户明确要求不增加计划书字数）。
4. D 档路线播种优化 → 不做，见 ADR-003。
5. 删除 rest / free 块 → **P2**（无 `candidate_id`，重算后无法稳定回放，见坑 #3）。
6. 块级新增任意景点 → **不可行**，走现有 `search_spots` → `select` → `plan`（坑 #7）。
7. 编辑 `route` / `unknown_route` / `transport` / `arrival` / `transfer_plan` / `meal` / `spot_continue` → **不可行**（坑 #8、#14）。
8. 块级 version / 协同编辑 → 不做（现有并发模型已串行化，见 §5.4）。
9. 自由拖拽排序 → 不做，用 ↑/↓ 按钮（`DESIGN.md` §6）。
10. 离线编辑、块类型转换、duplicate、块内富文本 → 不做。

---

## 1. 架构总览

### 1.1 分层

```
┌─────────────────────────────────────────────────────────┐
│ frontend/views/plan.js  +  frontend/core/icons.js       │  成员二
│   渲染 / 事件委托 / 局部 DOM 手术 / 乐观反馈              │
└───────────────────────┬─────────────────────────────────┘
                        │ POST /api/workspaces/{wid}/actions（唯一写入口）
┌───────────────────────▼─────────────────────────────────┐
│ app/api/workspaces.py      action 白名单 + revision 409   │  成员二
│ app/travel/dispatch.py     HANDLERS 路由                  │  成员二
│ app/travel/handlers/planning.py   do_edit_block 等        │  成员二
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│ app/planning/block_edits.py   【本次唯一新增排程侧模块】  │  成员三（架构出 Spec）
│   stamp / ensure_ids / find / rechain / check_day        │
│   replay / rebuild_preview / apply                       │
└───────────────────────┬─────────────────────────────────┘
                        │ 只调用，不修改
        ┌───────────────┼───────────────┬─────────────────┐
        ▼               ▼               ▼                 ▼
 timeline_tools    engine._generate   plan_revision    daily_schedule
 .prepare()        (preview=True)     .check()         （**零改动**）
```

### 1.2 分档判据（一条规则）

> **该操作是否改变「某一天的景点有序集合」？**
> - **否 → C 档**：`rechain()` 纯时间链平移级联。无 LLM、无路线查询、<1s。
> - **是 → D 档**：写 `visit_analysis` → `_generate(preview=True)` → evidence 回填 → 合并。无 LLM，有路线查询，1–3s。
> - **涉及新增未采集过的地点 → 不提供**，路由到现有生成链路。

MVP 内：**`edit_block` / `add_block` = C 档；`remove_block`(spot) = D 档。**

---

## 2. 点名文件与归属

### 2.1 成员三（`app/planning/`）—— **既有文件 0 行修改**

| 文件 | 操作 | 说明 |
|---|---|---|
| `app/planning/block_edits.py` | **新增**（约 260 行） | 编排层。向下只调现成的 `timeline_tools.prepare()` / `engine._generate(preview=True)` / `plan_revision.check()`。**不 import、不修改 `daily_schedule.py` 内部**。 |
| `app/planning/plan_routes.py` | **本轮不动** | 路线播种优化见 ADR-003 |

### 2.2 成员二（服务端集成 + 前端）

| 文件 | 操作 | 行数 | 说明 |
|---|---|---|---|
| `app/api/workspaces.py` | 修改 | +3 | action 白名单加 `edit_block` / `remove_block` / `add_block`（`workspaces.py:119-157`） |
| `app/travel/dispatch.py` | 修改 | +6 | `HANDLERS` 加 3 条；三者均加入 `DIRECT_ACTIONS` |
| `app/travel/handlers/planning.py` | 修改 | +80 | 3 个 `do_*`；`do_plan` / `do_optimize_plan` 各加 1 行 `block_edits.stamp(w["plan"])` + 回放闸门 |
| `app/application/action_policy.py` | 修改 | +1 | 三个动作归入 `QUIET_ACTIONS` |
| `app/application/guidance.py` | 修改 | +8 | 三个动作的 `VIEWS` 映射（均 `plan`）与进度文案 |
| `app/application/job_results.py` | 修改 | +6 | 把 `result.block_cascade` 挂进 `ui["block_cascade"]` |
| `frontend/views/plan.js` | 修改 | +180 | **主战场**：块四行结构、操作区、evidence `<details>` + 空态、级联变更条、阻断提示、撤销提示 |
| `frontend/core/state.js` | 修改 | +6 | `blockEditingId`、`blockDraft`、`expandedBlocks:Set`、`editRevision` |
| `frontend/core/icons.js` | **新增** | +70 | Lucide path 常量表 + `icon()` 单一出口。规格见 §7.2 |
| `frontend/index.html` | 修改 | +2 | ① 引入 `tokens.css`（**必须先于其他 stylesheet**）② 引入 `core/icons.js`（两者都必须先有文件再加声明，否则 `page_assets.py` 启动崩溃） |
| `frontend/styles/product.css` | 修改 | +120 | 块样式、操作区、evidence 折叠、锁定态 |
| `tests/test_block_edits.py` | **新增** | +180 | C 档纯函数单测 + D 档端到端 + 全部错误分支 |

### 2.3 前置阻塞项（Phase 2 开工前必须完成，属设计师/成员二）

1. `frontend/styles/tokens.css` **已存在但未在 `index.html` 声明** → 必须加 `<link rel="stylesheet" href="/assets/styles/tokens.css" />`，且放在 base.css 之前。
2. `base.css:1`、`base.css:914`、`workspace.css:2`、`product.css:2` 四个 `:root` 未清理 → `tokens.css` 不生效。
3. `frontend/core/icons.js` 未建；三处符号字符未替换为 SVG：太阳符号 U+2600（`views/workspace.js`）、汉堡菜单符号 U+2630（`index.html`）、勾号 U+2713（`components/workbench.js`）。
   > 存量符号替换列为**独立工作流**，不阻塞块编辑，可后做。

### 2.4 明确不动

`app/core/contracts.py`、`app/application/report.py`、`app/knowledge/**`、`app/agents/intent_contract.py`（28 种意图不变）、`app/agents/edit_tools.py`（选择层编辑工具不变）。

---

## 3. 数据契约

### 3.1 块稳定标识 `id`

- 生成后由 `block_edits.stamp(plan)` 为**每个 event** 赋 `id = uuid4().hex[:12]`，一次性写入。
- 遗留计划（无 id）在首次块操作时由 `ensure_ids(plan)` 懒回填，随编辑一起持久化。
- **禁止用 `(date, index)` 寻址**：插入/删除后索引漂移，会改错块（坑 #3）。

### 3.2 `plan['block_edits']`（人工修订记录）

> 命名遵循 team-lead 裁定：项目里 `revision` 已是 workspace 版本号语义，故用 `block_edits`。

```json
{
  "block_edits": [
    {
      "id": "be_9f3c1a2b7e01",
      "at": "2026-03-05T14:22:31",
      "op": "duration",
      "source": "user_explicit",
      "replayable": true,
      "superseded": false,
      "target": {
        "kind": "spot",
        "candidate_id": "B0FFH7",
        "block_id": "a1b2c3d4e5f6",
        "date": "2026-04-02"
      },
      "before": { "duration": 90, "start": "10:30", "end": "12:00", "note": "..." },
      "after":  { "duration": 150 }
    }
  ]
}
```

| 字段 | 规则 |
|---|---|
| `op` | `duration` \| `note` \| `remove` \| `add_free` \| `regen_all` |
| `source` | **固定 `"user_explicit"`**，复用 `app/core/contracts.py:248` 的 `SOURCE_USER` 词表，不新造 |
| `replayable` | **回放定位主键是 `candidate_id`**。`spot` = `true`；`rest`/`free`/`add_free` = `false`（无 candidate_id，重算后无法稳定定位） |
| `superseded` | 被后续修订覆盖或"全部重新生成"时置 `true`，**不清空**（保留审计与 `before` 快照） |
| `after` | **只存用户真正拥有的值**（`duration` / `note` / `name`）。`start`/`end` 是派生值，**禁止存入**——存了会与级联结果打架 |
| `before` | 完整快照，同时作为撤销依据 |

### 3.3 可操作性矩阵（UI 与后端必须一致，杜绝"部分能改"通病）

| kind | 可改时长 | 可改备注 | 可删除 | 可移动 | evidence 入口 | 说明 |
|---|---|---|---|---|---|---|
| `spot` | 应 | 应 | 应 | P2 | **应** | 主编辑对象 |
| `rest` | 应 | 应 | P2 | 禁 | 禁 | 含 `rest_type:"midday"`（午餐派生）与景点间机动两种 |
| `free` | 应 | 应 | P2 | 禁 | 禁 | 含用户自定义块 |
| `meal` | **禁** | 禁 | 禁 | 禁 | 禁 | **本轮新增判定**，见坑 #14 |
| `route` | 禁 | 禁 | 禁 | 禁 | 禁 | 派生事实，随前后块联动 |
| `unknown_route` | 禁 | 禁 | 禁 | 禁 | 禁 | 路线查询失败的占位段 |
| `transport` | 禁 | 禁 | 禁 | 禁 | 禁 | 固定锚点 |
| `arrival` | 禁 | 禁 | 禁 | 禁 | 禁 | 固定锚点 |
| `transfer_plan` | 禁 | 禁 | 禁 | 禁 | 禁 | 固定锚点（候车/安检预留） |
| `spot_continue` | 禁 | 禁 | 禁 | 禁 | 禁 | 防御性只读，见坑 #15 |

**不可操作的块必须显式说明原因**（`DESIGN.md` §4.2：虚线边框 + 锁图标 + `aria-describedby`，**不渲染 disabled 按钮**）。

---

## 4. 接口契约

### 4.1 统一入口（不新增 REST 端点）

全部走 `POST /api/workspaces/{wid}/actions`，body：`{revision, action, text, args, request_id}` → `202 {job_id}` → SSE `GET /api/jobs/{jid}/events`。

**理由**：现有写入路径已把「revision 乐观锁 → 单 workspace 串行 job → SSE 进度 → undo 快照 → 409 冲突」打包成一个契约（`app/api/workspaces.py:114-215` + `app/application/jobs.py:perform`）。再开同步 PATCH = 两套 revision 语义。

### 4.2 三个 action 的 `args`

```jsonc
// edit_block —— C 档（spot/rest/free）
{"date":"2026-04-02","block_id":"a1b2c3d4e5f6",
 "patch":{"duration":150},          // 15–720，单位分钟
 "confirm":false}                    // 阻断级冲突时置 true 才写入

// remove_block —— 仅 spot，D 档
{"date":"2026-04-02","block_id":"a1b2c3d4e5f6","confirm":false}

// add_block —— 仅 kind:"free"，C 档
{"date":"2026-04-02","after_block_id":"a1b2c3d4e5f6",
 "kind":"free","name":"逛超市","duration":60,"note":"","confirm":false}
```

`confirm` 语义（落地 PRD 6.4 阻断级）：
- 缺省/`false` → 计算级联；若有阻断级冲突 → **不写入**（revision 不变），返回 `status:"blocked"`
- `true` → 写入；越界项进 `plan["planning_issues"]`，沿用现有 `revision_day_end` 形状（`plan_output.py:57-76`），计划书仍可导出且保留提醒

### 4.3 级联响应（挂 `ui["block_cascade"]`）

```json
{
  "status": "applied",
  "cascade": [
    {"block_id":"...","name":"...","kind":"spot","date":"2026-04-02",
     "before":{"start":"10:30","end":"12:00"},
     "after":{"start":"10:30","end":"13:00"},"delta_minutes":60}
  ],
  "summary": {"affected_count":3,"shift_minutes":60,"day_end_estimate":"19:20"},
  "pending_routes": [{"from":"八大关","to":"栈桥","reason":"未查询，暂按30分钟占位"}]
}
```

- 阻断级走现有 `ui["conflict"]`（`job_results.py:19-20` 已有通道，`timeline.js:104` 已有渲染）→ **零新端点、零新 UI 组件**
- `day_end_estimate` 计算口径与 `plan_output.py:47-56` 一致：取非 `("transport","arrival","transfer_plan","free")` 且无 `route_scope` 的 event 的最大 `end`

### 4.4 错误契约

业务错误走 `DataError` → `j.error`；并发错误沿用 HTTP。

| 码 | 级别 | 触发 |
|---|---|---|
| `block_not_found` | failed | `block_id` 不存在或不属于该 `date` |
| `block_locked` | failed | 命中只读 kind |
| `block_out_of_range` | failed | `duration` ∉ [15, 720]，或目标日期不在 `visits.dates(w)` |
| `block_anchor_conflict` | **阻断** | 级联触及锚点且前一块新 `end` 越过锚点 `start` |
| `block_day_end` | **阻断** | 超出 `day_end` |
| `block_return_conflict` | **阻断** | 违反返程接驳约束 |
| `block_meal_window` | warning | 平移把餐次挤出窗口（**不静默吞掉**，见坑 #6） |
| `block_day_boundary` | **阻断** | 级联后越过 24:00（坑 #12） |
| `plan_stale` | failed | `plan["stale"]` 为真时拒绝编辑，提示先重新生成 |
| `plan_outdated` | failed | `duplicate_plan` 为真（父级景区已拆分） |
| revision 不匹配 | **409** | 现有 `workspaces.py:189` |
| 有活跃任务 | **409** | 现有 `workspaces.py:172-175` |

**降级文案统一（team-lead 裁定 #8）**：evidence 为空时前端渲染
> `未检索到官方资料，需自行核实`
> 系统没有检索到该景区的官方页面。出发前请自行核实开放时间、门票与预约要求。

带 `alert-triangle` 图标 + `--warn-soft` 底（`DESIGN.md` §5）。**禁止**"暂无数据"类空洞占位，**禁止**模型补写。

---

## 5. 级联引擎（F0 底座）

### 5.1 常量

```python
# app/planning/block_edits.py
EDITABLE  = frozenset({"spot", "rest", "free"})
ANCHORS   = frozenset({"transport", "arrival", "transfer_plan"})   # 固定锚点，级联在此停止
DERIVED   = frozenset({"route", "unknown_route", "meal", "spot_continue"})
MIN_DURATION, MAX_DURATION = 15, 720
```

### 5.2 `rechain()` —— C 档核心，纯函数，可单测

```python
def rechain(events, from_index, delta):
    """把 from_index 之后每个块整体平移 delta 分钟；遇第一个锚点停止。

    返回 (shifted_rows, hit_anchor_or_None)。
    抛 AnchorConflict：平移后前一块的 end 越过锚点 start。
    """
    rows = []
    for i in range(from_index, len(events)):
        e = events[i]
        if e.get("kind") in ANCHORS:
            if i and minute(events[i - 1]["end"]) > minute(e["start"]):
                raise AnchorConflict(
                    block=e,
                    overrun=minute(events[i - 1]["end"]) - minute(e["start"]),
                )
            return rows, e          # 锚点及其后一律不动
        before = (e.get("start"), e.get("end"))
        e["start"] = clock(minute(before[0]) + delta)
        e["end"]   = clock(minute(before[1]) + delta)
        rows.append({
            "block_id": e.get("id"), "name": e.get("name"), "kind": e.get("kind"),
            "before": {"start": before[0], "end": before[1]},
            "after":  {"start": e["start"], "end": e["end"]},
            "delta_minutes": delta,
        })
    return rows, None
```

### 5.3 锚点规则（可测的精确定义）

1. `ANCHORS = {transport, arrival, transfer_plan}`。
2. 级联从被改块**向后**遍历，遇到第一个锚点即停止；**锚点及其后所有块一律不动**。
3. 停止时若前一块的新 `end` > 锚点 `start` → `AnchorConflict`（阻断级）。
4. 实测锚点只出现在天的两端：去程 `transport` 在 index 0（`daily_schedule.py:118-130`）、`arrival` 在 index 0（`daily_schedule.py:178`）、返程 `transfer_plan`/`transport` 在末尾（`daily_schedule.py:288,968`）。所以"停止 + 后续不动"语义干净——**你不可能把火车推走**。
5. **派生块（`route` / `unknown_route` / `meal`）参与平移**，只是不可被用户直接编辑。

### 5.4 一致性断言 `check_day()`

```python
def check_day(day):
    """级联后必跑。返回硬错误列表（空 = 通过）。"""
    errors, prev_end = [], None
    for e in day["events"]:
        s = minute(e.get("start"))
        end_m = minute(e.get("end"))
        if end_m <= s:
            # 跨夜：仅 transport 允许（plan 层没有 end_date 字段，见坑 #13）
            if e.get("kind") != "transport":
                errors.append(("invalid_duration", e))
                continue
            end_m += 1440
        if prev_end is not None and s < prev_end:
            errors.append(("overlap", e))
        if end_m > 1440 and e.get("kind") not in ANCHORS:
            errors.append(("day_boundary", e))          # 坑 #12
        prev_end = end_m
    return errors
```

落地位置：C 档与 D 档写入前统一跑 **`app/planning/plan_revision.check()`**（`plan_revision.py:111`，已校验时间重叠 / 固定日期时段 / 当日结束 / 餐次窗口 / 景点集合完整性），`check_day()` 作为其**前置**快速失败。**块编辑与全量修订共用同一套门禁**。

### 5.5 D 档 `rebuild_preview()`（删除 spot）

```python
async def rebuild_preview(w, changes, progress):
    from app.planning.timeline_tools import prepare
    from app.planning.engine import _generate
    from app.planning import plan_revision
    working = prepare(w, changes)                    # 复用现成校验 + 翻译层（已有测试）
    plan = await _generate(working, progress, preview=True)
    plan = _restore(plan, w.get("plan"))             # 注意：见下方 _restore 说明
    hard = [i for i in plan_revision.check(working, plan) if i.get("level") != "warning"]
    if hard:
        raise DataError("修订后的安排仍有具体条件需要调整，原计划已保留。",
                        {"issues": hard, "view": hard[0]["view"]})
    return plan

def _restore(plan, old):
    """preview 产物不能直接覆盖保存的 plan。"""
    # 1) evidence 按 candidate_id 回填（preview 路径不带 evidence_ids，见坑 #2）
    by_cid = {e["candidate_id"]: e.get("evidence") or []
              for d in (old or {}).get("days", []) for e in d.get("events", [])
              if e.get("candidate_id")}
    for d in plan["days"]:
        for e in d["events"]:
            if e.get("candidate_id") in by_cid:
                e["evidence"] = by_cid[e["candidate_id"]]
    # 2) 保留旧值：title / created / review / usage
    for k in ("title", "created", "review", "usage"):
        if old and old.get(k) is not None:
            plan[k] = old[k]
    # 3) 清除 preview 标记
    plan.pop("preview", None)
    return plan
```

### 5.6 F3 人工修订保护（回放）

```python
def replay(plan, edits):
    """把 replayable 且未 superseded 的用户设定写回重算后的 plan。"""
    applied, missed = [], []
    for row in edits or []:
        if row.get("superseded") or not row.get("replayable"):
            continue
        cid = (row.get("target") or {}).get("candidate_id")
        event = _find_by_candidate(plan, cid) if cid else None
        if event is None:
            missed.append(row); continue
        for k, v in (row.get("after") or {}).items():
            event[k] = v
        event["edited"] = True
        applied.append(row)
    for date in {_date_of(plan, r) for r in applied}:
        rechain(_events_of(plan, date), 0, 0)     # 触发重排并按锚点校验
    return {"applied": applied, "missed": missed}
```

**闸门**：`do_plan` / `do_optimize_plan` 在生成前检查 `w["plan"].get("block_edits")` 是否有 `replayable` 且未 `superseded` 的条目；若有且 `args` 未带 `regen_choice` → 抛冲突，前端展示「保留我的修改 / 全部重新生成」。
**AC-4.3 补充（架构裁定）**：回放后若产生阻断级冲突，**不得静默写入**，必须回用户逐项确认。

---

## 6. 存储影响

| 项 | 结论 |
|---|---|
| 块级 version | **不加**。写入已串行化（`LOCKS[wid]` `jobs.py:60` + DB `status='running'` `workspaces.py:172` + revision 409）；块级 version 会引入第二套并发语义 |
| `dirty` 标记 | **不加**。`plan["stale"]` 已承担"计划过期"语义 |
| `plan["stale"]` | **块编辑后绝不能置 True**（坑 #1：导出 409）。`timeline_tools.apply()` 有置 stale 先例（`timeline_tools.py:215,261`），**D 档不得复用 `apply()`** |
| 块 `id` | **必须加**（§3.1） |
| `plan["block_edits"]` | **新增**（§3.2） |
| 块上 `edited: bool` | **加**，区分"系统建议 / 你改过" |
| 快照体积 | 每次块编辑产生全量快照。evidence 正文单条最多 6000 字符（`retrieval.py:38`），单快照可能 100KB+。MVP 可接受，本轮不做保留策略 |

`duplicate_plan`（`spot_hierarchy.py:133`）判据是"计划含父级景区且已被拆分"，**与 `selected_spots` 变化无关** → 块编辑不会误触发 `present()` 的 stale 置位。已核对，无冲突。

---

## 7. 设计 Token

> **本节以设计师产出为唯一来源**：`docs/design/DESIGN.md`（颜好看）+ `frontend/styles/tokens.css`。
> 架构侧只做约束性转述，不重复定义数值。

### 7.0 技术禁区（CSP 实测，硬约束）

| 禁区 | 证据 | 后果 |
|---|---|---|
| **任何 webfont CDN（Google Fonts / Inter / Noto Sans SC）** | CSP `style-src 'self'`（`app/api/security.py:33`）阻断 `@import` | 字体只能用本地系统栈 |
| **图标走 npm 包或 CDN** | CSP `script-src 'self'` + 无构建步骤 | 只能内联交付 |
| **新增资源未先建文件就加 link** | `app/api/page_assets.py:33-36` 对每个声明资源 `read_bytes()` | **文件缺失 = 启动崩溃** |
| **手工登记 `ASSET_VERSIONS`** | 它在 `app/api/security.py:18`（**不在 `main.py:23`**），由 `page_assets.py` 解析 `index.html` 自动生成 | 多余操作；只需在 index.html 声明 |

### 7.1 颜色

- 所有颜色走 `var(--token, #fallback)`，禁止裸 hex。
- **生效色板是 `product.css:2`，不是 `base.css:1`**——架构侧 v1 曾误引 `base.css:1-10`，已更正。四个 `:root` 同特异性（均为 (0,1,0)），`index.html` 加载顺序 base→workspace→product，**最后加载者胜**：

  | 变量 | `base.css:1`（**死代码，不生效**） | `product.css:2`（**今日真实生效**） |
  |---|---|---|
  | `--green` | `#2c6652`（绿） | **`#3657b5`（蓝）** |
  | `--ink` | `#203d35` | **`#263249`** |
  | `--muted` | `#738078` | **`#778195`** |
  | `--bg` | `#f6f4ed`（奶油） | **`#f6f7fa`（冷灰）** |
  | `--line` | `#dce2d7` | **`#e5e8f0`** |

- **架构侧对 A/B 案的裁定：走 A 案（`product.css` 蓝色，零视觉跳变）。** 理由：① 用户今天看到的就是蓝+冷灰，B 案是全站改色；② 本轮范围是"块编辑 + 攻略展开"，顺带改品牌色属于范围外的镀金；③ A 案风险最低。
- 新代码用 `--accent`，**不要用 `--green`**（它是蓝色的历史命名）。一屏内 `--accent` 可见使用 ≤ 2 处。
- **两处 WCAG 修复无论选哪案都强制生效**：`--muted` 3.92 → 5.46；新增 `--line-strong #80899e`（3.51）作为交互块边界，`--line` 仅作装饰分隔线。

### 7.2 图标

**唯一来源 = `frontend/core/icons.js`**（Lucide ISC 许可的 path 常量表 + `icon()` 单一出口）。

> **形态裁定经过一次反复，此为终裁**：架构侧先提 `icons.js`，后采纳设计师的 sprite，设计师随后又采纳回 `icons.js`。**终裁为 `icons.js`**，理由：① `views/*.js` 本来就返回 HTML 字符串，`icon()` 返回字符串可直接拼进 `innerHTML`；② **可单测**（PRD 可测试性是 P0，sprite 无法单测）；③ 单一具名出口便于用静态扫描强制执行"不得硬写 `<svg>`/emoji"。**两套方案不得并存。**

`icon()` 实现规格（设计师给定，照此实现，否则描边风格会散）：

```js
icon(name, { size = 16, className = "", label = "" })
// 产出：<svg class="icon ..." width/height={size} viewBox="0 0 24 24"
//        fill="none" stroke="currentColor" stroke-width="2"
//        stroke-linecap="round" stroke-linejoin="round" focusable="false"
//        [aria-hidden="true" | role="img" + <title>{label}</title>]>
```
- `stroke="currentColor"` 是硬要求：图标写死颜色就无法跟随锁定态/禁用态
- `label` 为空 → `aria-hidden="true"`（装饰性）；非空 → `role="img"` + `<title>`
- 尺寸 16（行内/徽标）/ 20（按钮内）/ 24（独立图标按钮）
- 任何文件不得硬写 `<svg><path>` 或 emoji（扫描须为零）

**本轮图标清单（20 个，含设计师追加的 6 个）**：
`square-pen` `trash-2` `plus` `arrow-up` `arrow-down` `chevron-down` `chevron-up` `clock` `x` `rotate-ccw` `external-link` `book-open` `info` `alert-triangle` `grip-vertical`
+ `lock`（锁定块）`map-pin`（spot 种类）`utensils`（meal 种类）`route`（route/transport 种类）`shield-check`（用户已设定标记）`check`（保存成功）

> 存量符号替换（`sun` / `menu`）列为**独立工作流，不计入这 20 个**，不阻塞块编辑。`check` 两边共用，只 vendor 一份。

### 7.3 禁止清单

emoji 作功能图标；紫色→粉色渐变；圆角 ≥24px；弹跳缓动；靠颜色单独传达可编辑性或块种类（WCAG 1.4.1：种类必须"图标 + 可见文字标签"，颜色只作辅助）。

> **待 team-lead 补发 Token 清单后覆盖本节。** 当前以 `tokens.css` 实际内容为准；开工前置项见 §2.3。

---

## 8. 已知坑（逐条内嵌，一条不能漏）

### 8.1 首轮识别（11 条）

| # | 坑 | 硬约束 |
|---|---|---|
| 1 | **`plan["stale"]` 陷阱（最高危）** | 块编辑后置 stale 会让用户编辑完立刻无法导出（`workspaces.py:225` 409）。D 档**禁止复用** `timeline_tools.apply()`（它置 `stale=True`），必须自写薄版本 |
| 2 | **D 档 evidence 静默清空** | preview 路径 `propose()` 走 `provisional()`，不带 `evidence_ids` → `daily_schedule.py:593` 算出空数组。必须按 `candidate_id` 回填，**必须有回归测试** |
| 3 | **块 id 缺失 → 改错块** | 索引在插入/删除后漂移（off-by-one）。必须先 `ensure_ids()` 再寻址 |
| 4 | **删除 spot ≠ 删事件** | 语义是取消选择，必须走 `selections.remove_selection` 同步 `selected_spots`，否则 `plan_revision.check()` 的 `set(seen)==set(active_ids)` 恒失败，计划书与工作台分裂 |
| 5 | **同日调序须清 period**（P2 留痕） | `provisional()` 的 `rank()` 按 period→visit_order→sequence→距离 排序。保留 `morning/afternoon` 混合会覆盖用户顺序。须统一 `period:"any"` + `sequence=1..n` + `not_before=None`；用户 pin 过 period 的除外（`block_pinned`） |
| 6 | **平移可能把餐次挤出窗口** | 落地前必跑 `plan_revision.check()`；餐次冲突是 **warning 级**（`plan_revision.py:230`），允许落地并明示，**禁止静默吞掉** |
| 7 | **禁 块级新增景点不可行** | 需候选采集 + 模型写 note + RAG 检索。路由到 `search_spots` → `select` → `plan` |
| 8 | **禁 编辑派生块不可行** | `route`/`unknown_route`/`transport`/`arrival`/`transfer_plan` 是已查询的派生事实（带 `source.queried_at`）或班次事实，改它 = 补造数据 |
| 9 | **禁 evidence 为空时模型补写不可行** | 违反项目铁律。必须显式降级为「未检索到官方资料，需自行核实」 |
| 10 | **路线查询配额** | D 档触发路线查询（N pair × 3 modes，Semaphore 3）。连续操作会消耗高德配额（已有 `ProviderBudgetRepository` 限流）。前端做 300ms 防抖 |
| 11 | **`innerHTML` 整块重绘丢状态** | `plan.js:151` 整页重绘会丢 `<details>` 展开态、滚动位置、焦点。按 `DESIGN.md` §6 做「快照 → 重绘 → 恢复」三步，展开态存 `expandedBlocks:Set` |

### 8.2 本轮复核新增（8 条）

| # | 坑 | 硬约束 |
|---|---|---|
| 12 | **`time_values.clock()` 不截断** | `clock(1470)` → `"24:30"`，而前端 `planMinute`（`plan.js:2-10`）只认 `hours===24 && minutes===0`。级联必须**显式校验 24:00 边界**（`check_day` 的 `day_boundary`），不能依赖 `clock()` |
| 13 | **plan 层没有 `end_date`** | `end_date` 只在时间轴表示 `plan_rows` 里有（`schedule.py:753`）。plan 的 `days[].events` 里跨夜班次表现为 `end <= start`，**必须靠这个反推**，且仅 `kind=="transport"` 允许；其他 kind 出现即错误 |
| 14 | **`meal` 事件真实存在但被简报与 PRD 遗漏** | `meal_events.py:137` 产出 `kind:"meal"`。team-lead 简报的 8 种 kind 与 PM PRD §5.1 均无 `meal`，而 `DESIGN.md` §4.1 标为"可编辑/可删除/可移动"——**三方不一致**。架构裁定：**MVP 的 `meal` 为只读**，理由是餐次时刻由 `meal_choices`（选择层事实）+ 餐次窗口 + 游玩收尾共同决定，块级改会与 `w["meal_choices"]` 失同步。"我不想吃这顿"应走现有 `meal_choice{mode:"remove"}`。**需 PM 改 PRD §5.1/§7.3、设计师改 `DESIGN.md` §4.1** |
| 15 | **`spot_continue` 防御性只读** | 仅 `plan_revision.py:136` 与 `schedule.py:688` 引用，当前无生产者（历史遗留）。按只读处理，避免未来复活时成为漏洞 |
| 16 | **`rest` 有两种语义** | `rest_type:"midday"`（午休，由午餐派生，`meal_events.py:154`）与景点间机动（`daily_schedule.py:724`）。改时长/删除的语义不同，MVP 均标 `replayable:false` |
| 17 | **打印会漏出攻略** | `plan.js:118` 的 `beforeprint` 强制展开 `.book details:not(.day-map)`。必须改成 `:not(.day-map):not(.block-guides)`，并加 `@media print { .block-guides { display:none } }`。否则打印 PDF 会把整段攻略灌进去，与"展开内容不进导出"冲突 |
| 18 | **图标交付形态经过一次反复，终裁 `icons.js`** | 架构侧先提 `core/icons.js` → 采纳设计师的 sprite → 设计师又采纳回 `icons.js`。**终裁 `frontend/core/icons.js`**（可单测、单一具名出口、字符串可直接拼 `innerHTML`）。**两套不得并存**，实现前必须先确认 Spec §7.2 与设计侧一致 |
| 19 | **改完前端必须重启服务** | `ASSET_VERSIONS` 是**启动时**算的 sha256（`security.py:18` + `page_assets.py`），不重启浏览器拿旧缓存 |
| 20 | **守卫测试目前不存在** | `tests/test_design_tokens.py` 与 `tests/test_browser_regression.py` **都不存在**（HANDOVER.md 描述的是计划中的守卫，非已生效）。**不要以为改坏会被拦住**。若 Spec 依赖它们做门禁，本轮必须补建 |
| 21 | **`base.css:1` 是死代码** | 四个 `:root` 中 `product.css:2` 胜出。按 `base.css` 色板实现会导致全站变色（详见 §7.1） |

---

## 9. 端到端验证（完成定义）

```bash
# 前置：tokens.css 已 link、四个 :root 已清理、sprite 已注入 → 重启服务
# 1. 启动（端口 8767），登录，进入 ≥2 天、≥4 个已选景点的工作区
# 2. 生成计划书
#    断言：plan.days[*].events[*] 全部含非空 id；spot 事件含 evidence 数组
pytest tests/test_block_edits.py -k stamp

# 3. C 档：edit_block 改某 spot duration +60
#    断言：该块 end 后移 60；其后所有块（含 route/meal/rest）同步后移；
#          无重叠；plan["stale"] 仍为 False；导出接口仍 200
pytest tests/test_block_edits.py -k rechain

# 4. C 档：add_block 加 free 块
#    断言：插入位置正确；后续级联；check_day 无硬错误；block_edits 记 replayable:false

# 5. D 档：remove_block 删一个 spot
#    断言：selected_spots 同步移除；新路线 A→C 已查询（route.minutes 非空）；
#          evidence 回填后非空 ← 回归点（坑 #2）
pytest tests/test_block_edits.py -k remove_spot

# 6. 阻断级：制造超出 day_end 的编辑
#    断言：confirm=false → status:"blocked" 且 revision 未变；
#          confirm=true → 写入且 planning_issues 含 revision_day_end

# 7. 锚点：编辑导致触及 transfer_plan
#    断言：AnchorConflict；锚点 start/end 未变

# 8. 错误分支：remove_block 一个 route 块 → block_locked；
#    stale 计划编辑 → plan_stale；旧 revision → 409

# 9. F3 回放：改 2 处 duration → 触发重新生成 → 选择「保留我的修改」
#    断言：两处用户值保留；未修订部分已重算；冲突时回到用户确认

# 10. 撤销：编辑后 action("undo")
#     断言：全字段恢复，含所有级联块的 start/end

# 11. 降级：找 evidence 为空的景区 → 前端渲染「未检索到官方资料，需自行核实」，
#     页面无模型生成文本
# 12. 打印：Ctrl+P 预览 → 攻略区不出现（坑 #17）
# 13. P0 扫描（须为零）
grep -oP "[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]" frontend/**/*.js frontend/index.html
```

**完成定义** = 端到端验证全通过 + EARS 验收标准全满足 + 回归率为零。

---

## 10. 测试清单（每条 EARS 至少一个用例）

| AC | 测试 |
|---|---|
| AC-1.1 / 1.2 / 1.3 / 1.4 / 1.5 / 1.6 | `test_remove_spot_*`（6 个） |
| AC-2.1 / 2.2 / 2.3 / 2.4 / 2.5 | `test_evidence_*`（前端快照 + 后端数据不改写断言） |
| AC-3.1 / 3.2 / 3.3 / 3.4 | `test_edit_duration_*`（4 个） |
| AC-4.1 / 4.2 / 4.3a / 4.3b / 4.4 | `test_block_edits_replay_*`（5 个） |
| AC-5.1 / 5.2 / 5.3 | `test_undo_*`（3 个） |
| AC-6.1 / 6.2 / 6.3 | `test_edge_*`（3 个） |
| 非功能·一致性 | `test_check_day_*`（含跨夜 transport、`24:00` 边界、锚点停止） |
| 坑 #2 回归 | `test_remove_spot_preserves_evidence` |
| 坑 #12 回归 | `test_rechain_rejects_past_midnight` |
| 坑 #13 回归 | `test_check_day_overnight_transport` |

**变异加固**（防沉默逻辑错误）：把 `rechain` 的 `delta` 取反、把 `ANCHORS` 清空、把 `check_day` 的跨夜判定去掉——三个变体必须各自让至少一个测试变红。
