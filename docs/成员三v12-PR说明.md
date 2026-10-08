# PR：成员三 v12 统一时间引擎与联动修复

## 基线

| 项目 | 值 |
| --- | --- |
| 仓库 | `Tao-feng233/Smart-travel-planning` |
| 目标分支 | `feat/shitu-v11-review-integration`（当前 `9d38e09`） |
| 基线提交 | `9d38e090d89af400564e53464c5d2b85a4fc7731`（已 rebase 到最新整合分支） |
| 工作分支 | `feat/shitu-v12-planning` |
| 提交数 | 11 |
| 测试 | 整合分支基线 181 → **229 全部通过**（新增 48 条，无删除） |

> 说明：本分支最初基于 `40374bc`，已完成 rebase 对齐到最新整合分支 `9d38e09`
> （含成员一的数据服务升级与山东语料、`e8b8ddb` 的分工交接文档）。
> rebase 后无需人工解冲突；整合分支的 181 条测试与本文新增的 41 条全部通过。

创建 PR：
https://github.com/Tao-feng233/Smart-travel-planning/pull/new/feat/shitu-v12-planning

对比链接：
https://github.com/Tao-feng233/Smart-travel-planning/compare/feat/shitu-v11-review-integration...feat/shitu-v12-planning

## 变化（按提交）

### 1. `c15dd0d` 新增统一时间模块
`app/time_policy.py`：纯函数，不访问数据库、不新增供应商调用。输出
`minutes / status / basis / unverified / evidence_ids`，状态三态
`verified / estimated / needs_check`。`schedule.windows()` 与
`foods.infeasible()` 改调该模块；班次变更（`transport_id` 不一致）不再复用旧值。

### 2. `5d83ac0` 首尾日按实查接驳路线计算
- 抵达日：`到达 + 90` → `time_policy.arrival_ready()`（到达 + 出站取行李 +
  车站→首站实查路线 + 机动）。
- 返程日：5 处 `出发 − 120` → `time_policy.return_preparation()`（末站→车站
  实查路线 + 候车/值机 + 机动）。
- 生成提示词里教模型的固定值一并删除。
- 站点坐标来源：工作区已有坐标直接用；没有则通过数据服务的
  `search_transport_places` 取候选（每个方向一次），仍取不到才走
  `needs_check` 并列出待核实项。

### 3. `807ad65` 模型两次排不开时确定性重排
可调整景点由程序重新分配日期；用户指定日期时段保持不动；有界深度优先
放置（先放大件、优先放剩余最多的日期），节点数有上限。

### 4. `e33bb37` 重排容量与规划阶段同口径
原实现用 `windows()` 上界（最长可到当天 24:00）当可排分钟，不扣餐次与
通行，也不受每日结束与返程截止约束。新增 `schedule.capacity()`、
`schedule.day_limit()`；`proposals.day_overload()`/`groups_overload()` 在
重排后用同一把尺子复核，仍超容量时给出可读冲突（含当日可排分钟与依据），
不再交给规划阶段悄悄压缩时长或跳过景点。

### 5. `39acb91` 餐次口径统一
`access.check` 的固定 +15 与 `planning.meal` 的 `round_up(15)`/relaxed 10
分钟不一致，会导致预检查放行、生成报超时。新增
`planning.meal_allocation()`/`route_allocation()` 作为唯一来源，预检查、
景点通行、时间轴餐次共用一个窗口与缓冲口径。

### 6. `c1264ca` 预算三分类
`planning.build_budget()` 输出 `verified / estimated / unknown`：起价是
带区间与覆盖说明的估算，房型报价标明覆盖日期是否与本次入住一致，未知项
逐条给原因，人均只按明确口径计算。计划书与前端按三类分别展示。

### 7. `9efe81e` 未确认返程与内部状态
`journey.return_date_status()` 区分 `confirmed` 与 `suggested`；建议态下
该日接驳准备降为 `needs_check`，warning 与 `time_policy.notes` 写明待确认。
`agent` 的返程候选筛选只在用户明确给出返程日时才做上界过滤。被跳过景点
的记录改为本地列表，并在入口清理历史遗留字段，不再落库。

### 8. `3e69510` 餐次绑定语义
两类餐次：`fixed_date`（固定日期，任何重排不挪期，旧记录按此处理）与
`follow_spot`（明确跟随某景点，保存 `bind_spot_id` 与绑定方式）。景点改期、
移除或日期未定时，`foods.binding_status()` 按当前安排现算 `affected`，
只提示并保留餐厅选择；景点改回原日期时状态自动解除。跟随餐次查餐厅时用
绑定景点作参照点。时间轴、计划书与前端都展示绑定方式与受影响原因。

## 需要的数据字段（请协调者提供）

| 输入 | 用途 | 缺失时行为 |
| --- | --- | --- |
| 车站/机场实体坐标（`kind` 为 `station`/`airport`/`transport_hub`，名称等于班次的 `arrival_station`/`departure_station`） | 查询"末站→车站""车站→首站"道路耗时 | 已接数据服务的 `search_transport_places`：取不到时返回 `needs_check` 并在 notes 列出待核实项，准备时长沿用旧兜底（90/120）；不猜坐标、不把未知当零 |
| 承运方候车/值机规则 | 替换 `WAIT_REQUIREMENTS`（航班 120、高铁 30、普速 45） | 使用估计值，依据写明"一般建议" |
| 儿童票价规则 | 预算里把交通从"未知"升级为估算 | 交通保持 `unknown`，不套成人价 |

## 调用方法

```python
from app import time_policy, schedule

ready  = time_policy.arrival_ready(transport, route_minutes)      # 缺依据传 None
prep   = time_policy.return_preparation(return_transport, route_minutes)
cutoff = time_policy.return_cutoff(departure_minutes, prep)
cap    = schedule.capacity(w, date)      # 当天可排分钟（唯一容量来源）
limit  = schedule.day_limit(w, date)     # 每日结束与返程截止取更早者
```

生成后 `w['time_policy']` 与 `plan['time_policy']` 携带同一份口径：

```json
{
  "unit": "minutes", "timezone": "Asia/Shanghai", "schema_version": 1,
  "arrival":  {"2026-10-12": {"minutes": 70, "status": "verified", "basis": "…", "transport_id": "…"}},
  "return":   {"2026-10-14": {"minutes": 160, "status": "verified", "basis": "…",
                              "station": {"id": "hub", "name": "青岛北站", "location": "120.38,36.10",
                                          "location_status": "verified"},
                              "route": {"mode": "walking", "minutes": 20, "polylines": []},
                              "transport_id": "…"}},
  "return_date_status": {"date": "2026-10-15", "status": "suggested", "basis": "…"},
  "notes": ["…"]
}
```

## 验收样例（自动化用例）

| 场景 | 结果 | 对应用例 |
| --- | --- | --- |
| 相同 16:00 返程，末站→车站 20 分钟 | 活动须在 13:20 前结束（准备 160 分钟，verified） | `test_time_policy.py` |
| 相同 16:00 返程，末站→车站 80 分钟 | 活动须在 12:20 前结束（准备 220 分钟，verified） | `test_time_policy.py` |
| 同样 20 分钟接驳，高铁 / 航班 | 准备 70 / 160 分钟，依据文本不同 | `test_time_policy.py` |
| 车站→首站 20 / 80 分钟 | 抵达日首个事件 13:25 / 14:25 | `test_time_policy.py` |
| 站点坐标取不到（无候选/多个同名） | `needs_check`，准备 120 分钟并注明"待替换"，未猜坐标 | `test_time_policy.py`、`test_station_lookup.py` |
| 站点坐标由数据服务候选提供 | 每方向只查一次并写回；坐标标 `candidate`、纳入接驳路线查询 | `test_station_lookup.py` |
| 四个 100 分钟景点被模型堆在同一天 | 重排摊到多天，逐日不超容量 | `test_day_capacity.py` |
| 预算（列表起价 480、实际 2 晚） | `estimated` 约 ¥960，`verified` 为空，5 项 `unknown` 各带原因 | `test_budget_disclosure.py` |
| 无返程班次 | `suggested`，计划警告"返程日期尚未确认"，不再当既定条件 | `test_return_date_status.py` |
| 预检查与生成对同一餐次的结论 | 相同 `minutes_needed` 与可行判定 | `test_meal_consistency.py` |
| 跳过景点 | 计划里点名，工作区无内部状态残留 | `test_skip_state_is_local.py` |
| 固定日期 vs 跟随景点餐次 | 固定不挪期；跟随景点改期只提示且保留餐厅；旧记录按固定日期 | `test_meal_binding.py` |

## 已知边界

1. 候车/值机与出站取行李仍是估计值，等承运方规则确认后替换常量。
2. `schedule.capacity()` 的通行开销按每天一个保守估计（`TRANSFER_DAY_MINUTES=60`），
   不是逐段实查；每天景点很多、路段很长时仍可能在规划阶段收窄时长，此时会
   明确列出被跳过的景点与原因（不静默删除）。
3. 未确认返程时仍按游玩天数生成行程骨架，只是标为待确认；没有改成"先问再生成"。
4. 本期未做 `schema_version` 迁移器与 `expected_revision` 写入门槛（属成员二范围）。
5. `rebalance` 是有限顺序比较，不承诺全局最优；节点数上限 20000，超限即放弃并给出原因。
6. 跟随餐次只做"日期跟随"：景点改到哪天，餐次就提示哪天受影响；不自动改写
   餐次日期，也不自动重查餐厅（重查由用户确认后触发）。
7. 餐次绑定不含"跨天跟随"：景点与餐次不在同一游玩日期范围时只提示受影响。

## 旧记录处理

- 旧工作区没有 `time_policy` 字段：按旧兜底（抵达 +90、返程 −120）计算并标
  `needs_check`，数值与旧版本一致，不会突变。
- 旧工作区遗留的 `_day_skips` 字段在生成入口被清理，不再混入新一轮警告。
- 计划新增 `time_policy`、`return_date_status` 字段；旧字段
  `budget.hotel_reference` 保留为估算合计，`budget.unknown` 由字符串改为对象，
  计划书与前端已同步。
- 旧固定值断言按业务语义改写（`test_interaction_v5` 的房型报价断言、
  `test_interaction_v7` 的批次调用次数、`test_experience_v11` 的
  `validation_feedback` 断言），未删除任何用例。

## 与两条并行线的对齐

| 对接方 | 状态 | 本分支的处理 |
| --- | --- | --- |
| 成员一（数据与知识服务） | 已合入整合分支 `9d38e09`：父子块混合检索、Qdrant、山东语料、`search_transport_places`（车站/机场坐标候选） | 已 rebase 并对齐；`retrieve_guides` 的 `guide_conditions` 调用保留。已接入：`time_policy.resolve_station()` 每个方向查询一次并写回班次记录，候选坐标标 `candidate` 并纳入接驳路线查询；`terminal_confirmed=false`，多个同名候选时不挑第一个 |
| 成员二（Agent 与业务系统） | `feat/shitu-v12-platform` 第一批已推送（`022c259`、`a1cd8f0`），审查报告列出 3 项规范 + 6 项需求问题，**尚未合入整合分支** | 本分支不依赖其 `app/contracts.py`；等公共契约合并后再按 `TimeProfile` 字段名对齐 `time_policy` 的输出结构 |
| 数据字段（站点坐标） | 原基线里站点实体没有坐标 | 已通过 `search_transport_places` 解决，见下一行 |
| 日期字段对齐 | 审查报告要求"日期草稿与成员三确认" | 本分支已提供 `time_policy`（抵达/返程口径、`transport_id`、`return_date_status`）作为成员二日期字段的输入；建议其 `DRAFT` 日期字段直接引用，不要另写一套推算 |
| 站点接驳坐标 | 已随整合分支提供候选工具 | `time_policy.resolve_station()` 每个方向只查一次并写回班次记录；候选标 `location_status='candidate'`、`terminal_confirmed=false`，多个同名候选不挑第一个；已有坐标则不再查询供应商 |
