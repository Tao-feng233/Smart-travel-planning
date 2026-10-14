# 识途 TravelSense — 项目交接文档

> 面向接手的开发者 / AI。读完本文应当能独立启动、修改、验证与交付本项目。
> 撰写时间：2026-10-09　撰写人：成员三（zzh）　基线提交：`064046a`
> 本文所有数字均为实测结果，不是估算。

---

## 0. 状态快照（先看这张表）

| 项 | 当前值 |
|---|---|
| 项目根目录 | `D:\ShiTu`（唯一目录，2026-10-09 由 `D:\ShiTu-v12` 重命名而来） |
| Git 分支 | `feat/shitu-v12-platform` |
| HEAD | `064046a`　ci: 加 GitHub Actions，自动跑后端与浏览器回归 |
| 远程 | `https://github.com/Tao-feng233/Smart-travel-planning`（**团队仓库，只读约定见 §12**） |
| 工作树 | 干净（无未提交修改） |
| 未推送 | `feat/shitu-v12-platform` 领先远程 **1 个提交**（即 `064046a` 本身） |
| 后端测试 | **413 passed / 4 skipped**（93 秒） |
| 服务 | `http://127.0.0.1:8767`，`GET /api/healthz` → `{"status":"ok","service":"shitu",...}` |
| Python | `.venv`（3.13.14），路径 `D:\ShiTu\.venv` |
| 端到端结论 | **能生成旅游规划书**（已实跑导出 5301 字符 markdown），但**有硬约束，见 §11** |

---

## 1. 项目是什么

**识途**是面向自由行用户的交互式旅行规划 Agent。通过自然语言 + 可视化工作台完成：
需求收集 → 景点选择 → 住宿房型 → 往返交通 → 餐饮安排 → 旅行地图 → 计划书生成，
并保存用户偏好、选择与版本历史。

### 1.1 团队与分工

三人小组，仓库 `Tao-feng233/Smart-travel-planning`。

| 角色 | 负责范围 | 主要分支 |
|---|---|---|
| 协调者（组长） | MCP、RAG、数据采集、公共契约合并 | `main` / 整合分支 |
| 成员二 | MySQL 业务存储、独立 Worker、日期状态、地图 SDK、应用集成 | `feat/shitu-v12-platform` |
| **成员三（本人）** | 统一时间引擎、动态时长、推荐与排程、餐次联动、局部重排、可信预算 | `feat/shitu-v12-planning` |

**成员三的职责边界**（`docs/collaboration/成员三任务说明.md`）：
主责 `planning.py`、`proposals.py`、`schedule.py`、`access.py`、`visits.py` 及新增时间模块；
`foods.py` 的餐次、`choices.py` 的规则、`agent.py` 的推荐部分为**共享边界**，改时拆小提交。
**不越界**：不替换 MySQL / MCP / 向量库，不重写地图底图和日期文本解析。

### 1.2 版本演进

v11.2（复核整合版）→ v12 平台化。v12 分三批推进，当前**第一批**：
仅 `app/contracts.py` 公共接口 + 测试 fixture，业务代码未大改。

---

## 2. 环境与启动

### 2.1 前置条件

| 组件 | 要求 |
|---|---|
| Python | 3.11+（便携包实测 3.13.9；本机 `.venv` 为 3.13.14） |
| MySQL | **可选**。`.env` 配了 `DATABASE_URL` 才会启用平台层，不配则沿用 SQLite |
| Node | 仅浏览器回归脚本需要（配 `playwright-core`） |
| 网络 | 需访问 DeepSeek、高德、途牛、和风 |

### 2.2 安装

```powershell
cd D:\ShiTu
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env      # 然后手工填写各 key
```

首次初始化中文向量模型与知识索引（**只此一次需要下载**，约 90MB）：

```powershell
.\.venv\Scripts\python.exe scripts/build_knowledge_index.py --download-model
.\.venv\Scripts\python.exe scripts/check_data_service.py
```

### 2.3 启动

```powershell
# 方式一：双击（推荐，会自动检测已运行实例）
.\启动.cmd

# 方式二：命令行
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8767 --no-access-log
```

浏览器访问 `http://127.0.0.1:8767`，首次需注册账号并**保存恢复码**。

> `scripts/start.py` 会先探测 8767 是否已有本项目的健康服务（比对 `project_id`，
> 该值为根目录路径的 sha256 前 16 位）。**目录改名后 `project_id` 会变**，
> 旧实例不会被认作本项目，属正常现象。

### 2.4 `.env` 字段

| 字段 | 说明 |
|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | DeepSeek，默认 `https://api.deepseek.com` / `deepseek-flash` |
| `AMAP_API_KEY` | 高德 Web 服务（地点、路线、静态图） |
| `TUNIU_API_KEY` | 途牛 MCP（酒店、车次、航班、门票） |
| `TUNIU_API_KEY_FALLBACK` | 可选，主 key 失效时自动回落 |
| `TUNIU_DAILY_LIMIT` | 项目自设的 24 小时只读查询预算。**`.env.example` 建议 120，默认 40** |
| `QWEATHER_API_KEY` / `QWEATHER_API_HOST` | 和风天气；Host 必须换成账号实际分配的地址 |
| `QDRANT_URL` / `QDRANT_API_KEY` | 留空 = 本地持久化 Qdrant（单进程）；多 Worker 必须配服务端 |
| `RAG_INDEX_PATH` / `RAG_MODEL_CACHE` / `EMBEDDING_*` | RAG 索引与模型位置 |
| `DATABASE_URL` | 留空则不启用平台层；填了才有人连 MySQL |
| `WORKER_*` | Worker 租约、轮询、ID |

> ⚠️ 本机 `.env` 中**未设置 `TUNIU_DAILY_LIMIT`**，因此实际取默认值 **40**。
> 一次完整端到端约消耗 6～10 次查询，连续调试很容易触顶（届时应用如实报"本项目额度已用完"）。
> **建议本机调到 120**，与 `.env.example` 的建议一致。

---

## 3. 目录结构

```text
D:\ShiTu
├── app/                 47 个 Python 模块（后端全部逻辑）
├── frontend/            12 个文件，原生 JS + CSS，共约 1337 行，无构建步骤
├── tests/               43 个测试文件（pytest）
├── scripts/             启动、联调、采集、建索引、验收脚本
├── data/
│   ├── catalog/         目的地概览目录
│   ├── knowledge/       官方资料正文（可提交）
│   ├── knowledge-sources*.json   来源注册表
│   └── runtime/         69MB，**已 gitignore**：travel.db、向量索引、模型缓存、截图
├── docs/
│   ├── collaboration/   团队协作与交接（成员任务说明、待修事项）
│   ├── project-report/  面试技术资料、演讲稿、流程图
│   └── legacy/          旧仓库历史设计资料（ADR 0001-0006 等，不作为运行依据）
├── .github/workflows/ci.yml   3 个 job：backend / tokens / browser
├── CONTEXT.md           **按时间倒序的实现记录，必读**
├── 开发状态.md           详细进度
├── 官方接口核对.md        供应商接口实测核对
└── HANDOVER.md          本文
```

---

## 4. 模块地图（`app/`，47 个）

### 4.1 入口与编排

| 模块 | 行 | 职责 |
|---|---|---|
| `main.py` | 302 | FastAPI 路由、静态资源版本号、SSE 任务流 |
| `runner.py` | 226 | 一次 planner turn 的唯一入口，API 进程与 Worker 共用 |
| `agent.py` | 834 | 业务动作总分发（`handle`），30+ action 分支。**最大最复杂** |
| `goal_agent.py` | 158 | 语义目标 + 受控 observe/decide/tool 循环（最多 4 次后续决策） |
| `guidance.py` | 67 | 由实际任务与已存选择推导 UI 状态（view / cta / 进度文案） |

### 4.2 时间与排程（成员三主责）

| 模块 | 行 | 职责 |
|---|---|---|
| `time_policy.py` | 283 | **统一时间契约**：抵达可用时刻与返程准备时刻只在这里算。单位分钟，区间左闭右开 |
| `schedule.py` | 280 | 临时时间轴、餐次窗口、保守交通冲突检查 |
| `visit_analysis.py` | 338 | 已选景点集合的负担估算，预览与正式规划共用 |
| `planning.py` | 853 | **正式计划书生成**（最大的业务模块） |
| `proposals.py` | 234 | 长行程分批提案，每个已选 ID 校验一次 |
| `visits.py` | 57 | 带日期的游玩意向：建议可灵活，用户指定须校验 |
| `journey.py` | 194 | 确定性小检查：日期字段保护、持续偏好、唯一候选 |
| `stay_plan.py` | 418 | 逐晚住宿编排：先按天连成线路，再以每日收尾点为锚点推荐当晚住宿 |

### 4.3 计划修订与警告

| 模块 | 行 | 职责 |
|---|---|---|
| `plan_revision.py` | 143 | `optimize_plan`：对全部已存事实修订完整计划书 |
| `plan_warnings.py` | 55 | 可复核警告：仅经同意后才发布缓存草稿，15 分钟过期 |
| `diagnostics.py` | 97 | 把失败转成可操作提示，不归咎用户的合法选择 |
| `auto_selection.py` | 244 | 用户授权的代选；**交通永不在此委托** |

### 4.4 业务领域

| 模块 | 行 | 职责 |
|---|---|---|
| `discovery.py` | 169 | 有来源的目的地发现与 POI 推荐分页 |
| `foods.py` | 456 | 餐饮候选与按日期/餐次的选择（锚点跟随、兜底、取消） |
| `locations.py` | 96 | POI 坐标核验 + 保守的跨供应商酒店匹配 |
| `access.py` | 79 | 有限路段预检查；**供应商未知 ≠ 不可通行** |
| `choices.py` | 54 | 选择基于供应商快照；无预订操作 |
| `enrichment.py` | 104 | 供应商事实与未知分离于推荐 |
| `maps.py` | 105 | 鉴权静态地图（密钥不下发） |

### 4.5 数据 / RAG / 供应商

| 模块 | 行 | 职责 |
|---|---|---|
| `providers.py` | 376 | 供应商封装：高德 MCP、途牛 MCP（双 key 回落、45s 超时、13s 最小间隔） |
| `tools.py` / `tooling.py` | 22 / 29 | MCP stdio 管道，API 与 Worker 共用 |
| `mcp_server.py` | 65 | 项目自有的 MCP 工具 |
| `rag.py` | 69 | 父子块 BM25 + Qdrant 语义召回，RRF 融合，明确降级 |
| `knowledge.py` | 144 | 保源的父子语料与词项检索原语 |
| `knowledge_collection.py` | 92 | 受控采集（来源注册表，无开放爬虫） |
| `vector_index.py` | 91 | 版本化 Qdrant 代次，建完原子发布 |
| `embeddings.py` | 51 | 真实中文 ONNX 向量（BGE-small-zh）或兼容 API |
| `public_directory.py` / `public_fetch.py` | 143 / 68 | 静态页面解码、限速抓取、robots 检查 |
| `data_contracts.py` / `data_settings.py` | 46 / 21 | 数据侧 DTO 与配置 |

### 4.6 存储 / 任务 / 鉴权

| 模块 | 行 | 职责 |
|---|---|---|
| `storage.py` | 202 | SQLite：账户、旅行、选择、版本、任务、有限期缓存 |
| `contracts.py` | 211 | v12 第一批公共业务契约（5 个 Repository + JobContext） |
| `queues.py` | 48 | 决定动作在本进程还是 Worker 队列执行 |
| `auth.py` | 145 | 注册/登录/恢复码/scrypt/CSRF/限流 |
| `request_cache.py` | 49 | 同请求合并、HTTP 连接池 |
| `replies.py` | 95 | 公开回复通道：只发生成答案，不露模型推理 |
| `report.py` | 81 | 计划书 markdown 导出 |
| `config.py` / `text.py` | 14 / 3 | 配置与文本工具 |

### 4.7 前端（`frontend/`，无构建）

`index.html`(49) + `app.js`(235) + `workbench.js`(34) + `details.js`(55) +
`experience.js`(104) + `assistance.js`(67) + `account.js`(69) + `interactive-map.js`(77)
+ `style.css`(384) + `workspace.css`(164) + `product.css`(62) + `tokens.css`(37)

> `tokens.css` 是设计变量的**唯一来源**，`main.py` 的 `ASSET_VERSIONS` 中它排第一，
> `index.html` 中它必须在 `style.css` 之前引入。有 `tests/test_design_tokens.py` 静态守卫，
> 另有 `tests/test_browser_regression.py` 断言加载顺序。

---

## 5. 端到端业务链路

### 5.1 完整流程（已实测跑通）

```text
注册/登录
  → POST /api/workspaces                     建旅行会话
  → action=chat       "我在郑州，想X日到Y日去成都玩4天，2位成人，预算6000，喜欢美食和古迹"
  → action=select     逐个选景点（args.id 来自 spot_search.ids）
  → action=complete_spots                    确认景点 → 自动 search_hotels
  → action=select     选住宿（hotel_query.ids）
  → action=complete_hotel                    确认住宿 → 自动推荐往返车次
  → action=select     确认去程/返程（recommended → confirmed）
  → action=complete_food                     餐饮（可全部自行安排）
  → action=plan                              生成计划书
      ├ 若返回 pending_plan_warning → action=approve_plan_warning
      │   args 必须带 {approval_id, confirmed:true}
      └ 写入 w['plan']
  → GET /api/workspaces/{wid}/export         导出 markdown 旅游规划书
```

### 5.2 主要 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/healthz` | 健康检查，返回 `project_id` |
| POST | `/api/auth/register` `/login` `/logout` `/password` `/recover` | 账户 |
| GET | `/api/auth/me` | 当前用户 + `csrf_token` |
| POST | `/api/workspaces` | 建旅行 |
| GET | `/api/workspaces` `/{wid}` `/latest` | 列表 / 详情 / 最近 |
| PATCH / DELETE | `/api/workspaces/{wid}` | 改名归档 / 删除 |
| **POST** | `/api/workspaces/{wid}/actions` | **提交动作，202 + `job_id`** |
| GET | `/api/jobs/{jid}` | 轮询任务（非终态时不返回 workspace） |
| GET | `/api/jobs/{jid}/events` | **SSE 流式**（前端主要用这个） |
| POST | `/api/jobs/{jid}/cancel` | 取消 |
| GET | `/api/workspaces/{wid}/export` | 导出 markdown |
| GET | `/api/workspaces/{wid}/map-image` | 鉴权静态地图 |
| POST/GET | `/api/feedback` | 反馈 |
| GET/DELETE | `/api/account/export` `/api/account` | 数据导出 / 注销 |

### 5.3 合法 action 全集

```
chat  request_auto_selection  approve_auto_selection  continue_auto_selection
cancel_auto_selection  approve_plan_warning  cancel_plan_warning  requirements
discover_destinations  choose_destination  search_spots  spots_page  dismiss_spot
complete_spots  complete_hotel  skip_hotel  search_hotels  search_foods
meal_choice  complete_food  visit_schedule  analyze_visits  optimize_plan
select  select_room  hotel_detail  place_detail  weather  train  flight
ticket  plan  undo
```

### 5.4 鉴权与并发约束（写代码时注意）

- Cookie 名默认 `shitu_session`；非 GET 请求必须带 `X-CSRF-Token` 头，否则 403。
- 同一旅行同时只能有 1 个活跃任务（409）；同一用户最多 2 个（429）；全局 4 个（503）。
- 每用户每日最多 120 次任务（429）。
- **`revision` 必须匹配**，否则 409「旅行已更新，请刷新后重试」。
  **失败的 turn 也会 bump revision**，提交前必须重新拉取工作区。

---

## 6. 核心契约与红线（改代码前必读）

这些是项目反复强调的语义，**违反即产品失信**，不要"优化"掉。

| 术语 | 含义 | **禁止说成** |
|---|---|---|
| 选定 | 用户表达意向 | 购买、已预订 |
| 旅行计划书 | 每日安排 + 出发准备说明 | 已预订行程 |
| 推荐班次 | 真实查询预填的意向，`selection_status=recommended`；用户确认后为 `confirmed` | 已出票 |
| 旅行会话 | 一次旅行的规划记录 | 全站聊天记录 |

**数据红线**

1. **不补造数据**：查询失败、无结果、字段缺失三种情况分别处理，绝不填 0 或编造。
2. **不把未知当零**：缺坐标/接驳/承运规则时输出带依据的可调整估计或"待核实"。
3. **估算必标 `estimated`**：模型知识只能用于建议玩法与时长，不能补造运营事实。
4. **区间起价 ≠ 指定日报价**：`startPrice` 是区间起价，销售区间 ≠ 可预约名额。
5. **营业资料不保证出游当天状态**；人均不是门票价格。
6. **余票是查询时快照**，不能保证之后买到。
7. **资料采集时间 ≠ 未来适用日期**；旧快照限定当日的公告不当作当前事实。
8. **硬条件**（班次、预约、用户指定日期时段）不可被通用警告豁免；
   **软条件**（估算负担、分配不均）是可确认继续的警告。

---

## 7. 数据层

### 7.1 业务存储

- **SQLite** `data/runtime/travel.db`：账户、旅行、选择、版本、任务、供应商缓存、调用计数。
  - 关键表：`users` `sessions` `workspaces` `jobs` `calls` `cache`
  - `connect()` 采用**每线程复用连接**（Windows 上频繁关闭会截断 `-wal` 并报 readonly）。
- **MySQL**：`.env` 有 `DATABASE_URL` 才会启用；`app/infra/session.py` 默认
  `mysql+pymysql://root@127.0.0.1:3306/shitu_v12`。**本机 MySQL 正在监听 3306**（PID 12656）。
  `scripts/init_db.py --create` 建库。`tests/test_mysql_platform.py` 在不可达时自动 skip。

### 7.2 RAG / 知识库

- 语料：`data/knowledge/*.json`，全语料 **90 条记录 / 78 父块 / 181 子块**。
- 检索：**中文字符二元组 BM25 + Qdrant 语义召回（BGE-small-zh，512 维）→ RRF 融合 → 按父块聚合**。
- 分块：父块 ≤1400 字符，子块 ≤360 字符（重叠 50）。检索子块，返回父块。
- 索引按版本建新集合，写完原子切换 manifest；正文更新而向量未更新时**明确降级为 BM25**。
- 更新流程：`collect_knowledge.py` → `build_knowledge_index.py` → 看
  `data/runtime/knowledge-collection-report.json`。
- MCP 工具：`retrieve_guides`（支持 `visit_date` / `end_date` 区间与 `entity_ids` 严格过滤）、
  `search_transport_places`（车站/机场真实坐标候选）。

---

## 8. 外部供应商与实测边界

| 供应商 | 提供 | 关键实测结论 |
|---|---|---|
| 高德 | 地点、餐厅、营业资料、电话、人均、图片、路线、静态图 | 真实路线返回分钟数/距离/步骤/折线；请求间隔 ≥0.4s，并发 ≤2 |
| 途牛 | 酒店房型、车次、航班、门票 | **预售期硬约束见下**；实测"杜甫草堂"0 项、"成都杜甫草堂博物馆"40 项（混有附加商品） |
| 和风 | 天气与预警 | 超出预报窗口的日期保留待确认 |
| DeepSeek | 意图识别、JSON 提案、流式回复、独立审核 | `deepseek-flash` |

### 8.1 ⚠️ 途牛/铁路预售期（最容易翻车的一条）

**出发日超出约 15 天，所有车次余票恒为 0，导致无法选定班次 → 无法生成计划书。**

2026-10-09 实测郑州→成都：

| 出发日 | 距今天数 | 有票车次 |
|---|---|---|
| 2026-10-11 | 2 | 29 / 30 |
| 2026-10-20 | 11 | 29 / 30 |
| 2026-10-26 | 17 | **0 / 30** |
| 2026-11-02 | 24 | **0 / 30** |
| 2026-11-10 | 32 | **0 / 30** |

失败链：余票 0 → `complete_hotel` 的过滤 `str(p.get('seats')) != '0'` 滤掉全部车次 →
`select` 被 `transport_select` 以「该班次当前显示无票」拒绝 → 往返无法 confirmed →
`plan` 生成空（`days=0`）→ `export` 返回 400「请先生成计划书」。

**演示 / 验收必须用今天起 15 天内的出发日期。** 代码位置见 §11 的 D-1。

### 8.2 额度

途牛查询受 `TUNIU_DAILY_LIMIT`（本机默认 **40**）限制，另有 13 秒最小间隔与 45 秒超时。
超限后抛 `DataError('本项目的途牛查询预算已用完，请稍后再试')`。

---

## 9. 团队协作与分支

### 9.1 远程分支（已 fetch 到的）

```
origin/main                                  addb81e
origin/feat/shitu-v11-review-integration     1a81941  ← 协调者的整合分支
origin/feat/shitu-v12-arrival-and-return     f609c06
origin/feat/shitu-v12-planning               （成员三）
origin/feat/shitu-v12-platform               dfce5d3  ← 本分支的远程位置
origin/feat/shitu-v12-time-and-stay
origin/integrate/reviewed-contracts-food-20261009
origin/fix/shitu-review-csp-meal-guard
origin/feature/*                             （早期分支）
```

### 9.2 本地分支同步状态（2026-10-09）

| 分支 | 本地 | 远程 | 状态 |
|---|---|---|---|
| `main` | `addb81e` | `addb81e` | 同步 |
| `feat/shitu-v12-platform`（当前） | `064046a` | `dfce5d3` | **领先 1**（CI 提交未推送） |
| `feat/shitu-v11-review-integration` | `2a8c9c8` | `1a81941` | **落后 28** |

### 9.3 ⚠️ 与整合分支合并的重大风险（已实测两次失败）

- 同步 `review-integration @ 1a81941`：全量 `--theirs` → **136 failed**；
  逐文件挑选 → **150 failed**（分散在 12+ 个测试文件）。
- **根因是架构级差异**，不是函数缺失：整合分支引入了 `spot_hierarchy`、
  `travel_preview`、`timeline_review` 等一批新模块，重写了住宿/餐饮/时间轴的组织方式。
- 我的 417 条测试是围绕**我的实现**写的，对齐到他的架构等于重写 300+ 条测试。

**结论：不要单方面硬合。应由协调者统一整合，或先把测试对齐到他的架构。**
两次尝试均已 `git reset --hard` 回滚，备份标签 `backup/v12-integration-attempt-150fail`。

我的独有贡献（合并时需保留）：`meal_alignment`（锚点餐次跟随）、
`foods.anchor_spot`、`infeasible` 实查口径、`tuniu_keys` 双 key 回落、
`schedule.plan_rows`（`travel_preview` 依赖）。

---

## 10. 测试与验证

### 10.1 跑测试

```powershell
cd D:\ShiTu
.\.venv\Scripts\python.exe -m pytest -q        # 413 passed, 4 skipped，约 93 秒
```

`pytest.ini`：`testpaths = tests`，`norecursedirs = repository-backups dist .venv data`。

### 10.2 三层验证

| 层 | 内容 | 如何跑 |
|---|---|---|
| 静态 | `test_design_tokens.py`：tokens.css 唯一 `:root`、变量全部有定义、裸 `var()` 必须有兜底 | 默认跑 |
| 后端 | 417 条用例（413 passed / 4 skipped），覆盖业务/契约/排程/餐饮/住宿/地图/RAG | 默认跑 |
| 浏览器 | `scripts/browser_regression.cjs`（5 组断言：账户隔离、token 加载顺序、餐饮兜底、不可行原因、景点回填） | **默认跳过**，需同时满足：服务已起 + `SHITU_BROWSER_TESTS=1` + `NODE_PATH` 指向含 `playwright-core` 的 node_modules |

浏览器回归是**可失败**的（已用人为制造的 3 个回归验证过），不是"跑一遍打印结果"。
注意：纯 API 测试测不出 UI 断裂（曾出现改了 `data-meal-remove` 属性名 API 测试仍全绿），
所以关键交互都补了 DOM 断言。

### 10.3 CI（`.github/workflows/ci.yml`，119 行）

3 个 job：`backend`（pytest + junit 产物）、`tokens`、`browser`。
> 坑：早版在 `run: |` 里用 `exit 0/1`，会终止整个 job 且显示绿色。
> 已改为写 `$GITHUB_OUTPUT` 标记 + 后置 `if` 判断。

---

## 11. 已发现缺陷与待办

### D-1（P0）预售期外无法生成计划书 ⭐ 最影响演示

- 现象：出发日 > 约 15 天 → 无法确认往返 → `plan` 空 → `export` 400。
- 位置：`app/agent.py` `complete_hotel` 中
  `candidates=[p for p in ... if str(p.get('seats'))!='0' and ...]`，
  以及 `transport_select` 的「该班次当前显示无票」拒绝。
- 建议修法：**区分「余票 0」与「未开售」**。预售期外仍按时刻表推荐，
  但明确标注"该日期尚未开售、余票待发售后再核实"。这不触碰"不声称能预订"的红线。
- 状态：**待决策**，未改（涉及产品口径，需团队确认）。

### D-2 途牛查询偶发超时

- 现象：`complete_spots`、返程查询出现过「途牛查询失败或超时」（45s 超时，**无重试**）。
- 建议：`providers._tuniu` 加一次幂等重试（注意 13s 最小间隔与额度计数不要重复计）。

### D-3 `complete_food` 流式回复中断

- 现象：「流式回复连接失败或中断，请重试」。偶发一次，不影响已保存的选择。

### D-4 返程日按推算导致末日空白

- `journey.travel_date()` 默认 `start_date + days`（4 天行程推到 10-16），用户未显式确认。
- 规划书已如实标注"待确认"，但最后一天因返程未定而整日空白，观感差。

### D-5 整合分支待修事项（协调者复核结论）

详见 `docs/collaboration/分支整合复核与待修事项-20261009.md`，要点：

| 优先级 | 问题 |
|---|---|
| P1 | Worker 最终发布在租约检查前就保存旅行，取消后仍写计划 |
| P1 | Worker 新旅行仍在 SQLite，MySQL jobs 外键对不上，入队失败会回退 API 执行 |
| P1 | 恢复阶段未把 JobContext 阶段读写接进查询/提案/规划 |
| P1 | 逐晚酒店：`assignment_map` 与界面不一致，路线与预算仍用单一主酒店 |
| P1 | 房型与警告：规划分支重新引入"强制选房型"和估算容量硬拒绝（应为可选 + 可确认警告） |
| P1 | Worker 身份：所有进程默认 `worker-local`，旧进程可借用新租约 |
| P1 | 供应商额度并发下非原子；知识实体过滤 SQL 自关联；导入版本写 0 |
| P2 | 知识适用范围未读 `scope.start/end`；餐饮兜底（**本次已修**） |

### D-6 我的分支独有、合并时需保留

`meal_alignment`、`foods.anchor_spot`、`foods.infeasible` 实查口径、
`providers.tuniu_keys` 双 key 回落、`schedule.plan_rows`。

---

## 12. 操作红线（用户明确要求，最高优先级）

1. **Git 提交/推送必须逐次授权**。
   用户说「commit / 提交 / 推送」之前，只允许只读操作（`status`/`diff`/`log`/`show`/`fetch`）。
   每次授权只对当次有效，**不得把上一轮同意当本轮同意**。
   报告内容须含：具体文件清单、每个文件改了什么、提交信息文案、目标分支/远程。
2. **删除文件必须精确到单个文件**：删前报告路径、确认唯一命中、做备份、删后复核 diff。
   禁止批量/通配删除（含 `rm -rf` 目录级）。
3. **不主动安装/下载任何东西**：装包、下模型、下工具前须说明体积与用途并获授权。
   用户有独立 Python 环境，不要擅装。
4. **不主动创建文件**：写文件前先说明写什么、写到哪里，经审批再写。
5. **只读对待团队仓库**：不得擅自 push 或改动他人代码。合并冲突按
   "自己的代码按自己的版本、他人代码按他人的版本"处理。
6. **临时脚本放 `%TEMP%`，用完即清**。
7. 不主动更新展示稿/手册/共享文档；Evals 评测集先跳过只记录。

---

## 13. 已踩过的坑（工程细节，能省你半天）

| 坑 | 表现与解法 |
|---|---|
| `curl` 在 Windows Git Bash 下对本服务返回**空 body** | 改用 Python `urllib`/`httpx`；并加 `--noproxy '*'` 或 `ProxyHandler({})` 绕本机代理 |
| 后台服务随 Bash 调用结束被回收 | 必须用**后台任务方式**启动（本会话用 `run_in_background`），否则下一个命令就连不上 |
| `revision` 409「旅行已更新」 | 每次 action 后（**包括失败的 turn**）都要重新 `GET /api/workspaces/{wid}` 取最新 revision |
| `approve_plan_warning` 报「请先在规划提醒窗口确认」 | args 必须带 `{'approval_id': pending['id'], 'confirmed': True}`，空 args 不行 |
| 目录改名后 `project_id` 变化 | 属正常；`scripts/start.py` 不会复用旧实例。`.venv/pyvenv.cfg` 的 `command=` 是记录性文字，可同步改，不影响运行 |
| Windows 目录重命名报 `Device or resource busy` / `Permission denied` | 先杀占用进程（python/node），**并确保没有 shell 的 CWD 停在该目录内** |
| 前端改了没生效 | `main.py:23` 的 `ASSET_VERSIONS` 是**启动时**按文件内容算的 sha256 前缀，改完前端**必须重启服务** |
| Edit 工具会把整个文件重写成 CRLF，污染 diff | 判别：`git diff --stat` 与 `git diff --ignore-cr-at-eol --stat` 数字不一致即有 CR 噪声；清理后再收尾 |
| `var(--x, #fff)` 写成 `var(--x), #fff` | 逗号必须在括号内，浏览器会静默忽略整条声明。有静态测试守着 |
| CI 里 `run: |` 内写 `exit 0` | 会终止整个 job 且显示绿色。改用 `$GITHUB_OUTPUT` |
| heredoc 里的正则反斜杠被 shell 吞掉 | 不要用 heredoc 写含正则的脚本，改用文件写入 |
| 本机 `git push` / `git fetch` 失败但 `curl api.github.com` 通 | 已知的本地 TLS 问题。可用 GitHub Git Data API（blob→tree→commit→ref）绕过 |

环境红线（历史，本机已规避但换了机器可能复现）：
- **torch 在本机被系统策略拦截**（`WinError 4551`），任何依赖 torch 的方案都放弃，用 `onnxruntime`。
- 删 Python 包前必看 `pip show` 的 `Required-by`：`huggingface_hub` 被 `tokenizers` 依赖、
  `sympy` 被 `onnxruntime` 依赖，按包名想当然删会直接搞坏 RAG。
- HuggingFace 直连被代理挡，必须用 `hf-mirror.com`；不用 `hf_hub_download`（符号链接创建失败）。

---

## 附录 A：真实端到端验证脚本

不 mock 任何接口，直连 8767，跑完会打印计划书体检并导出 markdown。
**2026-10-09 实测通过**（用 `2026-10-12` 出发日期），导出 5301 字符。

```python
"""识途端到端：需求 -> 景点 -> 住宿 -> 交通 -> 餐饮 -> 计划书 -> 导出。"""
import json, os, sys, time, urllib.error, urllib.request, uuid

BASE = os.environ.get('BASE', 'http://127.0.0.1:8767')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
COOKIE = CSRF = ''

def call(method, path, body=None, raw=False):
    global COOKIE
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json'); req.add_header('Origin', BASE)
    if COOKIE: req.add_header('Cookie', COOKIE)
    if CSRF and method != 'GET': req.add_header('X-CSRF-Token', CSRF)
    try:
        with OPENER.open(req, timeout=900) as r:
            sc = r.headers.get_all('Set-Cookie') or []
            if sc: COOKIE = '; '.join(c.split(';')[0] for c in sc)
            t = r.read().decode('utf-8')
            return r.status, (t if raw else (json.loads(t) if t else None))
    except urllib.error.HTTPError as e:
        t = e.read().decode('utf-8')
        return e.code, (t if raw else (json.loads(t) if t else None))

def wait(jid, limit=2400):
    for _ in range(limit):
        _, j = call('GET', '/api/jobs/' + jid)
        if j and j.get('status') not in ('queued', 'running'): return j
        time.sleep(0.3)
    raise RuntimeError('任务超时 ' + jid)

def refresh(w):
    _, latest = call('GET', '/api/workspaces/' + w['id'])   # 失败的 turn 也会 bump revision
    return latest or w

def act(w, action, args=None, text='', tolerate=False):
    st, body = call('POST', '/api/workspaces/%s/actions' % w['id'],
                    {'revision': w['revision'], 'action': action, 'text': text,
                     'args': args or {}, 'request_id': str(uuid.uuid4())})
    if st != 202:
        w = refresh(w)
        if not tolerate: raise RuntimeError('%s 提交失败 %s: %s' % (action, st, body))
        print('  [skip] %s -> %s' % (action, st)); return None, w
    job = wait(body['job_id'])
    print('  [%s] %s(%s)' % (job['status'], action, json.dumps(args or {}, ensure_ascii=False)[:50]))
    return job, (job.get('workspace') or refresh(w))

def main():
    name = 'e2e' + str(int(time.time()))[-8:]
    st, body = call('POST', '/api/auth/register',
                    {'username': name, 'password': 'Aa-test-' + name, 'nickname': '端到端'})
    assert st == 201, body
    globals()['CSRF'] = body['csrf_token']
    _, w = call('POST', '/api/workspaces', {})

    # ⚠️ 日期必须落在今天起约 15 天内，否则余票恒为 0，无法确认往返（见 §8.1）
    start, end = os.environ.get('DATE', '2026-10-12'), os.environ.get('END_DATE', '2026-10-15')
    _, w = act(w, 'chat', text='我在郑州，想%s到%s去成都玩4天，2位成人，预算6000，喜欢美食和古迹'
                               % (start, end))
    print('需求:', json.dumps(w.get('requirements'), ensure_ascii=False))

    ids = list((w.get('spot_search') or {}).get('ids', []))[:4]
    for cid in ids: _, w = act(w, 'select', {'id': cid})
    _, w = act(w, 'complete_spots')

    hotels = list((w.get('hotel_query') or {}).get('ids', []))
    if hotels: _, w = act(w, 'select', {'id': hotels[0]})
    _, w = act(w, 'complete_hotel' if w.get('hotel') else 'skip_hotel')

    for slot, direction in (('selected_transport', 'outbound'), ('selected_return', 'return')):
        if (w.get(slot) or {}).get('selection_status') == 'confirmed': continue
        pool = {}
        for key in ('train:' + direction, 'flight:' + direction):
            for p in ((w.get('transport_queries') or {}).get(key) or {}).get('items', []):
                pool[p['id']] = p
        items = sorted(pool.values(), key=lambda x: x.get('departure', ''))
        if items: _, w = act(w, 'select', {'id': items[0]['id']}, tolerate=True)

    _, w = act(w, 'complete_food', tolerate=True)
    _, w = act(w, 'plan', tolerate=True)
    pending = w.get('pending_plan_warning')
    if pending:   # args 必须带 approval_id 与 confirmed
        _, w = act(w, 'approve_plan_warning',
                   {'approval_id': pending['id'], 'confirmed': True}, tolerate=True)

    plan = w.get('plan') or {}
    print('计划书: stale=%s 天数=%d 待办=%d 提醒=%d 攻略=%d'
          % (plan.get('stale'), len(plan.get('days') or []), len(plan.get('todos') or []),
             len(plan.get('warnings') or []), len(plan.get('guides') or [])))
    st, text = call('GET', '/api/workspaces/%s/export' % w['id'], raw=True)
    print('导出:', st, len(text or ''), '字符')
    return 0 if (plan.get('days') and st == 200) else 1

if __name__ == '__main__': sys.exit(main())
```

运行：

```powershell
cd D:\ShiTu
.\.venv\Scripts\python.exe scripts\e2e_real_run.py
# 或指定日期（务必在 15 天内）
$env:DATE='2026-10-12'; $env:END_DATE='2026-10-15'
```

> 该脚本当前副本位于 `%TEMP%\shitu_e2e_full.py`（临时目录，可能被清理）。
> 若需长期保留，建议落到 `scripts/e2e_real_run.py`（**需先经用户同意再建文件**）。

---

## 附录 B：常用命令速查

```powershell
# 启动
.\启动.cmd
# 测试
.\.venv\Scripts\python.exe -m pytest -q
# 只跑 token 静态检查
.\.venv\Scripts\python.exe -m pytest tests/test_design_tokens.py -q
# 浏览器回归（三条件齐全）
$env:SHITU_BROWSER_TESTS='1'; $env:NODE_PATH='C:\Users\zzh\.workbuddy\binaries\node\workspace\node_modules'
.\.venv\Scripts\python.exe -m pytest tests/test_browser_regression.py -q
# 知识索引重建
.\.venv\Scripts\python.exe scripts\collect_knowledge.py
.\.venv\Scripts\python.exe scripts\build_knowledge_index.py
# 途牛当日额度自查
.\.venv\Scripts\python.exe -c "import sqlite3,time;c=sqlite3.connect('data/runtime/travel.db');print(c.execute('SELECT COUNT(*) FROM calls WHERE provider=? AND time>?',('tuniu',time.time()-86400)).fetchone()[0])"
# 只读 git
git status --short; git log --oneline -10; git branch -vv
```

---

## 附录 C：延伸阅读（按优先级）

1. `CONTEXT.md` — 按时间倒序的实现记录，**改任何功能前先搜这里**
2. `docs/collaboration/成员三任务说明.md` — 本人职责与验收条件
3. `docs/collaboration/分支整合复核与待修事项-20261009.md` — 当前待修清单
4. `docs/collaboration/数据与知识服务接入说明.md` — RAG / Qdrant 接入
5. `官方接口核对.md` — 供应商接口实测核对
6. `开发状态.md` — 详细进度
7. `docs/project-report/识途项目面试技术资料.md` — 对外讲解口径（v11）
8. `docs/legacy/DESIGN_CONTINUITY.md` — 旧仓库思想延续（不作为运行依据）
