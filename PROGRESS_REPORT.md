# 项目进度报告（三人协作版）

> 本文件是三条开发线的**共享进度台账**。每完成一步就在这里追加一条记录，
> 不删除历史记录；有变更就新增一条并在末尾说明覆盖了什么。

最后更新：2026-09-24

---

## ⚡ 最新变更（只看这一块就够）

**本次更新**：2026-09-24 · 步骤 3 进行中 —— v0.4 落地 + **TripProfileDraft 契约补全**

**仓库地址**：https://github.com/Tao-feng233/Smart-travel-planning

**这次发生了什么**

- 项目仓库整体搬到 `travel-planner-starter-pack-v0.4` 目录（v0.3 目录可删除）。
- 契约升级到 **v0.4**：`CONTRACTS.md` 重写，新增 `contracts/` 基线与 `fixtures/` 契约测试。
- 新增 5 份文档与 2 条 ADR，根目录只保留 4 份高频文件，其余进 `docs/`。
- **补齐了 v0.4 的一处硬伤**（原 Q1）：正式 `TripProfile` 保持关键字段必填，
  新增 `TripProfileDraft` 承载"还没问全"的画像，再用 `finalize_trip_profile` 转换。
  这样"缺日期/预算就追问"这条 P0 要求终于有了合法表达方式。
- 新增 4 个 fixture：不完整 Draft 合法、Draft 转 Profile 成功、强行转换失败、
  正式画像缺字段仍然非法。

**⚠️ A、B 请注意：现在开始必须遵守暂停规则**

`docs/SHARED_SCHEMA_HANDOFF.md` 规定：在 C 提交 `schema-v0.4` 之前，

- **不要**自己定义共享对象，**不要**用 `dict` 临时顶替，**不要**复制 `TripProfile` 等模型；
- 需要但还没有的对象，发 `SCHEMA_BLOCKER` 并暂停该部分；
- **可以继续做**：Vue 页面布局、Provider 内部实现、数据库连接、纯内部私有类型、不依赖缺失 Schema 的单元测试。

**本次结论**：v0.4 文档已就位；**C1 共享 Schema 重建是当前唯一阻塞项**，
完成后 A、B 才能全速推进。

**需要 A 行动**

- [ ] 读 `docs/SHARED_SCHEMA_HANDOFF.md`（暂停规则）与 `docs/DATA_PROVIDER_ARCHITECTURE.md`（Mock/快照/实时/混合四层）
- [ ] MCP 工具口径已由 v0.4 定死为 **9 个**（见 `CONTRACTS.md` §12），不需要再讨论
- [ ] 在 C 交出 `schema-v0.4` 前，只做 Provider 内部实现、数据库连接、Chroma 索引等不依赖共享 Schema 的部分

**需要 B 行动**

- [ ] 读 `docs/SHARED_SCHEMA_HANDOFF.md`，用暂停规则约束自己的 AI 助手
- [ ] 在 C 交出 `schema-v0.4` 前，只做 Vue 骨架、页面布局、不依赖共享对象的内部逻辑
- [ ] 任务口径有变：B5 从 `ChangeRequest` 改为 `UserAction`；
      B6 从"组装 TravelGuide"改为"把内部 `PlanNode/DayPlan` 富化为 `GuideNode/GuideDay` 与七部分攻略"

**需要三人共同确认**

- [ ] `docs/SCOPE_MATRIX.md` 作为 P0/P1 的唯一裁决源，其他文档不再各自定义优先级
- [ ] v0.4 §1.3 的枚举取值集合（C 按此实现，不再自行推断）
- [ ] 之前登记的契约待确认项中，有 4 条已被 v0.4 解决，见 `docs/contract-open-questions.md` 第 5 节

**已完成，不需要行动**

- 仓库与分支已建好（地址与分支见上方表格）
- 仓库已整理：根目录只保留 4 份高频文件，其余设计文档移入 `docs/`（导览见 `docs/README.md`）；
  原始需求文档归到 `docs/requirements/`，并附"需求 → 设计"对应表

---

## 0. 使用说明

### 状态标记

```text
✅ 完成    🔄 进行中    ⬜ 未开始    ⛔ 阻塞    ⚠️ 有风险/需确认
```

### 每步记录的固定格式

每条记录必须回答 `AGENTS.md` 要求的六个问题，缺一条视为该步未完成：

```text
1. 修改/新增了哪些文件
2. 实现了哪个业务流程
3. 使用了哪些契约对象
4. 运行了哪些测试，结果如何
5. 哪些数据或依赖仍是模拟实现
6. 是否影响其他成员的接口（否 / 是，说明影响）
```

### 三条开发线的边界（不得互相越界）

| 线 | 负责人 | 交付边界 | 分支 |
|---|---|---|---|
| A | 数据、RAG 与 MCP | 给定目的地、日期和偏好，返回符合 `ResourceCandidate` 的候选及证据 | `feature/data-rag-mcp` |
| B | LLM 决策与 Vue 前端 | 把用户输入变成 `TripProfile`/`ChangeRequest`，把验证后的计划组装成七部分 `TravelGuide` | `feature/llm-vue` |
| C | LangGraph、规划验证与后端集成 | 把 `TripProfile` + `ResourceCandidate` 变成经过验证的 `ItineraryPlan`，并提供 REST 接口 | `feature/graph-planner` |

### 仓库根目录约定

本目录即为**代码仓库根目录**，只保留四份每天都要动的文件：

```text
README.md            项目入口
AGENTS.md            AI 协作规则（每次开会话必读）
CONTRACTS.md         接口契约（改动需三人确认）
PROGRESS_REPORT.md   本文件
```

其余文档在 `docs/`（设计、规格、数据、计划、决策、原始需求），
交接材料在 `handoff/`，代码在 `backend/`、`frontend/`、`data/`。

### 分支同步约定（各自一台电脑，务必遵守）

```text
C 每完成一步 → 提交并推送 main → 再把三条 feature 分支同步到 main
```

- **在 A、B 尚未有自己的提交时**，C 可以直接把 `feature/*` 快进到 `main`（当前即如此）。
- **一旦 A、B 在自己的分支上提交过**，C 就**不得**再覆盖他们的分支；
  改为由各人自己合入主线：

  ```bash
  git checkout feature/你的分支
  git merge origin/main      # 把 C 的进度合进来
  ```

- 冲突时以 `CONTRACTS.md` 与 `backend/app/schemas/` 为准，改不动就找对方确认，
  不要各自新增临时字段。

---

## 1. 当前总览

| 模块 | 负责 | 目录 | 状态 | 最后更新 |
|---|---|---|---|---|
| 共享 Schema v0.3（旧版） | C | `backend/app/schemas/` | ⚠️ 将被 v0.4 替换 | 2026-09-24 |
| v0.4 契约基线模型（718 行） | 启动包 | `contracts/contract_models.py` | ✅ 已就位 | 2026-09-24 |
| v0.4 契约测试数据（13 个） | 启动包 | `fixtures/` | ✅ 已就位 | 2026-09-24 |
| **共享 Schema v0.4（C1）** | C | `backend/app/schemas/` | 🔄 **下一步，当前阻塞项** | — |
| 契约示例 Fixture（C/A 共用） | C | `backend/tests/fixtures/` | ✅ 完成 | 2026-09-24 |
| 原始需求文档归档 | C | `docs/requirements/` | ✅ 完成 | 2026-09-24 |
| 项目骨架与密钥配置 | C | `.gitignore`、`.env.example`、`backend/` | ✅ 完成 | 2026-09-24 |
| FastAPI + LangGraph（C2） | C | `backend/app/api/`、`backend/app/graph/` | ✅ 完成 | 2026-09-24 |
| 会话存储（内存 + JSON 快照） | C | `backend/app/services/session_store.py` | ✅ 完成 | 2026-09-24 |
| 缺失字段判定与追问策略 | C | `backend/app/services/missing_fields.py` | ✅ 完成 | 2026-09-24 |
| 模拟 MCP Client（A 线替换点） | C | `backend/app/services/travel_mcp_client.py` | ✅ 完成 | 2026-09-24 |
| TripProfile 提取（STUB，待 B 替换） | C→B | `backend/app/services/request_parser.py` | ⚠️ 临时实现 | 2026-09-24 |
| 目的地推荐（STUB，待 B 替换） | C→B | `backend/app/services/destination_recommender.py` | ⚠️ 临时实现 | 2026-09-24 |
| 前置过滤（C3） | C | `backend/app/services/` | ⬜ 未开始 | — |
| 行程生成（C4） | C | `backend/app/services/` | ⬜ 未开始 | — |
| 验证器（C5） | C | `backend/app/services/` | ⬜ 未开始 | — |
| 修复与重规划（C6） | C | `backend/app/services/` | ⬜ 未开始 | — |
| REST 集成（C7） | C | `backend/app/api/` | ⬜ 未开始 | — |
| MySQL 表与试点数据（A1） | A | `data/` | ⬜ 未开始 | — |
| Chroma 认知卡片（A2） | A | `data/` | ⬜ 未开始 | — |
| RAG 检索（A3） | A | `backend/app/services/`（A 区） | ⬜ 未开始 | — |
| MCP Server（A4） | A | `backend/app/mcp_server/` | ⬜ 未开始 | — |
| 地图/天气 Provider（A5） | A | `backend/app/providers/` | ⬜ 未开始 | — |
| 数据源可行性表（A6） | A | `docs/DATA_SOURCE_ASSESSMENT_TEMPLATE.md` | ⬜ 未开始 | — |
| 测试 Fixture（A7） | A | 待定 | ⬜ 未开始 | — |
| Vue 前端（B1–B7） | B | `frontend/` | ⬜ 未开始 | — |

---

## 2. P0 完成标准对照

来自 `TEAM_PROJECT_PLAN.md` 第 3 节。P0 未全部跑通前不得开始 P1。

| # | P0 要求 | 负责 | 状态 | 证据 |
|---|---|---|---|---|
| 1 | Vue 对话输入和行程展示 | B | ⬜ | — |
| 2 | LLM 输出结构化 `TripProfile` | B | ⬜ | — |
| 3 | 至少一次主动追问 | B/C | 🔄 C 侧已通 | `tests/test_graph_clarification.py`（B 侧前端待接） |
| 4 | RAG 检索并返回 `evidence_id` | A | ⬜ | — |
| 5 | LLM 只在 `planning_ready` 候选中推荐 | B | ⬜ | — |
| 6 | 至少一个 MCP 工具被 LangGraph 实际调用 | A/C | 🔄 C 侧已通 | `retrieve_destinations` 实际调用 `search_planning_ready_destinations`（当前为模拟实现） |
| 7 | 根据日期过滤闭馆或不可用景点 | C | ⬜ | — |
| 8 | 生成带时间、交通和预算的行程 | C | ⬜ | — |
| 9 | 验证并修复至少一种冲突（闭馆替换） | C | ⬜ | — |
| 10 | 用户修改后重新规划受影响部分（下雨） | C | ⬜ | — |
| 11 | 七部分 `TravelGuide` 由后端组装并在 Vue 展示 | B/C | ⬜ | — |

---

## 3. 已完成步骤记录

### 步骤 0：Git 仓库与分支搭建（协作基础设施）

| 项目 | 内容 |
|---|---|
| 日期 | 2026-09-24 |
| 执行线 | C（受全体委托） |
| 状态 | ✅ 完成 |
| 目标 | 建立三人各自一台电脑时的同步方式 |

**1）做了什么**

- 仓库根目录定为 `travel-planner-starter-pack`（`AGENTS.md`、`CONTRACTS.md` 所在层）。
- 远程：`https://github.com/Tao-feng233/Smart-travel-planning`。
- `main` 分支包含完整启动包、后端骨架、共享 Schema、契约 fixture、进度报告与交接文档。
- 建立并推送三条开发分支：`feature/data-rag-mcp`、`feature/llm-vue`、`feature/graph-planner`。
- 仓库内配置 HTTP 代理（`http://127.0.0.1:7897`，**仅本仓库生效**），因为本机直连 GitHub 超时。

**2）历史处理**

远程原有 3 个提交（早期需求文档）已通过 `git merge -s ours --allow-unrelated-histories`
并入历史，**项目内容以启动包为基准**。

> 2026-09-24 补充：原始需求文档已按最新要求**恢复**到 `docs/requirements/`
> （并附上"需求 → 设计"对应表），便于三人回溯某个功能当初为什么提出来。

**3）是否影响其他成员接口**

否。这是纯基础设施步骤，未改任何契约或代码。

**4）遗留**

本地 `C:\Users\HP\.git`（家目录被误初始化的空仓库）内容已移走，
家目录不再被 git 识别为仓库；剩余的空目录与 `.git.disabled-20260924` 待人工清理。

### 步骤 1：项目骨架 + 共享 Schema（C1）

| 项目 | 内容 |
|---|---|
| 日期 | 2026-09-24 |
| 执行线 | C |
| 状态 | ✅ 完成 |
| 目标 | 搭出后端骨架，冻结三条线共用的数据对象 |

**1）修改/新增的文件**

```text
.gitignore                                      密钥与构建产物不入库
.env.example                                    模型/地图/天气 Key 模板
backend/README.md                               C 线开发说明
backend/requirements.txt                        P0 技术栈依赖
backend/pytest.ini                              测试路径配置
backend/app/__init__.py
backend/app/api/__init__.py                     FastAPI 路由（占位）
backend/app/graph/__init__.py                   LangGraph（占位）
backend/app/services/__init__.py                服务层（占位）
backend/app/schemas/enums.py                    契约枚举
backend/app/schemas/contracts.py                核心契约对象
backend/app/schemas/guide.py                    TravelGuide 七部分
backend/app/schemas/mcp.py                      MCP 工具输入输出
backend/app/schemas/__init__.py                 统一导出（81 个符号）
backend/tests/fixtures/*.json                   11 份契约示例数据
backend/tests/test_contract_examples.py         契约示例校验测试
backend/tests/test_contract_strictness.py       契约约束测试
docs/contract-open-questions.md                 契约空洞登记
PROGRESS_REPORT.md                              本文件
```

**2）实现的业务流程**

本步不涉及业务流转，交付的是"数据对象层"。它使后续所有节点的输入输出可以被机器校验，
而不是靠人工对文档。

**3）使用的契约**

`CONTRACTS.md` 第 1–13 节全部实现：

```text
TripProfile / Budget / TravelerComposition / DestinationRequest
KnowledgeCoverage / DestinationRecommendation
ResourceCandidate / ResourceAvailability / TimeWindow
Evidence / TravelLeg / TripSegment / StaySegment / PlanNode / DayPlan
ItineraryPlan / PlanBudget / Conflict / RepairOption / PlanState
UserAction / ChangeRequestPayload
TravelGuide 七部分（TripSummary / IntercityOption / ArrivalPlan /
  PreparationItem / LodgingCandidate / CostItem / AlternativePlan 等）
MCP 六个工具的输入输出模型
```

另实现 26 个枚举，取值全部照抄文档，未自行增删。

**4）运行的测试**

```text
cd backend && python -m pytest
tests/test_contract_examples.py     19 passed
tests/test_contract_strictness.py   12 passed
合计 31 passed in 0.17s
```

环境：Python 3.12.7、pydantic 2.8.2、pytest 7.4.4。

**5）仍是模拟实现的数据或依赖**

- `backend/tests/fixtures/` 下全部数据为模拟数据，来源统一标记
  `source_type=MOCK` + `acquisition_status=MOCK_ONLY`，不伪装成已核验事实。
- 试点目的地暂用 `dest_chengdu`（成都），具体目的地清单待 A 线确认后替换。
- MySQL、Chroma、地图/天气 Provider 均未接入。

**6）是否影响其他成员接口**

**是（首次建立，非破坏性变更）**：`backend/app/schemas/` 从本步起成为三条线唯一的数据对象定义处。
A、B 两条线请通过 `from app.schemas import ...` 使用，不得复制定义或新增字段。

### 步骤 1 的遗留问题（需三人确认）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | 9 个字段只有示例值、没有取值集合（`pace`、`physical_intensity`、`Conflict.type`、`RepairOption.action`、`PlanState.stage` 等） | C3–C6 无法写出确定性规则，只能用字符串比较 | 优先补全 `CONTRACTS.md` 的取值集合 |
| 2 | MCP 输入的 `travel_dates`、`get_weather` 的 `temperature_range` 嵌套结构未定义 | 已做最小推断，A/C 两侧可能对不齐 | 确认后写回契约 |
| 3 | `CONTRACTS.md` 列 6 个 MCP 工具，`AI_TASK_PROMPTS.md` 只写 3 个 | A 线工作量口径不一致 | 以 6 个建模，P0 至少实现 3 个必须项 |

详细说明见 `docs/contract-open-questions.md`。

### 步骤 2：FastAPI + PlanState + LangGraph 状态图（C2）

| 项目 | 内容 |
|---|---|
| 日期 | 2026-09-24 |
| 执行线 | C |
| 状态 | ✅ 完成 |
| 目标 | 让"缺信息就追问"的回路真的能跑起来，并暴露 REST 接口 |

**1）修改/新增的文件**

```text
backend/app/core/config.py                        运行期配置（只读环境变量）
backend/app/core/__init__.py
backend/app/graph/stages.py                       PlanStage 阶段词汇表
backend/app/graph/context.py                      TurnContext（每轮上下文，不进契约）
backend/app/graph/nodes.py                        6 个节点 + 2 个条件边函数
backend/app/graph/workflow.py                     StateGraph 装配与单轮执行
backend/app/graph/__init__.py
backend/app/services/missing_fields.py            关键字段判定与追问文案
backend/app/services/request_parser.py            规则式 TripProfile 提取（STUB）
backend/app/services/destination_recommender.py   目的地推荐（STUB）
backend/app/services/fake_data.py                 模拟目的地/景点/证据（MOCK_ONLY）
backend/app/services/travel_mcp_client.py         MCP 客户端协议 + Fake 实现
backend/app/services/session_store.py             会话存储（内存 + JSON 快照）
backend/app/services/session_service.py           存储 + 工作流 + 回复组装
backend/app/services/reply_builder.py             状态 → 助手回复（纯函数）
backend/app/schemas/api.py                        REST 传输对象
backend/app/api/deps.py                           依赖注入与替换点
backend/app/api/routes.py                         会话类 REST 接口
backend/app/main.py                               FastAPI 应用入口
backend/tests/test_missing_fields.py              7 个用例
backend/tests/test_request_parser.py              14 个用例
backend/tests/test_travel_mcp_client.py           11 个用例
backend/tests/test_graph_clarification.py         9 个用例
backend/tests/test_api_sessions.py                7 个用例
```

**2）实现的业务流程**

```text
POST /api/sessions/{id}/messages  输入自然语言
  → parse_request          并入 TripProfile（只使用用户说过的话，不猜测）
  → check_missing_fields   计算 missing_fields
      ├─ 缺关键字段 → ask_clarification → 返回追问，等待补充
      └─ 信息齐全   → retrieve_destinations（调用 MCP 工具取候选）
                        ├─ 有候选 → recommend_destinations → 返回候选 + 证据
                        └─ 无候选 → report_insufficient_data（明确降级，不编造）
```

已实测的两轮对话（真实 HTTP 调用，不只单元测试）：

```text
第 1 轮「我想出去玩，不想早起」
  → ASKING_CLARIFICATION，追问：出发地 / 出发日期 / 返回日期 / 人数 / 预算
第 2 轮「从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，轻松一点」
  → AWAITING_DESTINATION_CONFIRMATION
  → 推荐成都（建议 5 天），证据 ev_101 / ev_301 / ev_302
  → 回复附带降级说明：当前数据源为模拟数据（MOCK_ONLY）
```

**3）使用的契约**

`PlanState`（LangGraph 状态本体）、`TripProfile`、`DestinationRecommendation`、
`ResourceCandidate`、`Evidence`、`KnowledgeCoverage`，以及 §12 的 MCP 工具
输入输出模型。REST 层新增传输对象 `AssistantReply` 等
（`backend/app/schemas/api.py`，属于接口层，不是领域契约）。

**4）运行的测试**

```text
cd backend && python -m pytest
80 passed = 原 31 个契约测试 + 新增 49 个

  test_missing_fields.py         7
  test_request_parser.py        14
  test_travel_mcp_client.py     11
  test_graph_clarification.py    9
  test_api_sessions.py           7
```

两次真实运行验证：`uvicorn app.main:app` 启动成功；
用 httpx 走完整两轮对话，中文往返正常。

**5）仍是模拟实现的数据或依赖**

| 依赖 | 现状 | 替换点 |
|---|---|---|
| MySQL + Chroma + 真实 MCP Server | 未接入 | `FakeTravelMCPClient` |
| 目的地/景点/证据数据 | 全部 MOCK_ONLY | `backend/app/services/fake_data.py` |
| LLM 提取 TripProfile | 规则式 STUB | `StubTripProfileParser` |
| LLM 目的地比较 | 规则打分 STUB | `StubDestinationRecommender` |
| 会话持久化 | 内存 + JSON 快照 | `InMemorySessionRepository` |

**6）是否影响其他成员接口**

**是（新增，非破坏性）**：

- 新增 REST 接口 `POST /api/sessions`、`POST /api/sessions/{id}/messages`、
  `GET /api/sessions/{id}`，B 线前端现在就可以对接。
- 新增两个**替换点协议**：`TripProfileParser`（B2）、`DestinationRecommender`（B4），
  B 线实现后 C 线零改动接入。
- 新增 MCP 客户端协议 `TravelMCPClient`，A 线按此签名实现真实 MCP Server。
- `TripProfile` 部分字段放宽为可选（见遗留问题 11），需三人确认。

### 步骤 2 的遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 11 | `TripProfile` 原本全字段必填，无法表示"还没问全"的状态，而"追问"要求画像能在补全过程中存在 | C 线已放宽为"除 `session_id` 外可空" | 三人确认后写回 `CONTRACTS.md` |
| 12 | `PlanState` 无法承载"本轮用户输入"与"中间检索结果" | C 线用 LangGraph 运行期上下文传递；前端看不到原始候选 | 若前端需要展示原始候选，需加字段或由 REST 层暴露 |
| 13 | 用户说"预算不限"时无法表达（`Budget.amount` 是必填数字） | 追问会重复询问预算 | 契约需要一种"不限"的表达方式 |
| 14 | REST 响应体（`AssistantReply` 等）在 `CONTRACTS.md` §14 未定义 | B 线只能照现有实现对接 | 确认后把响应体写进契约 |
| 15 | 用户点名一个数据不覆盖的目的地（例如都江堰）时，系统会改为推荐其他目的地 | 与用户预期不符 | C3/C4 阶段补"点名目的地不可用"的明确分支 |

### 步骤 3：迁移到启动包 v0.4 + 契约重写

| 项目 | 内容 |
|---|---|
| 日期 | 2026-09-24 |
| 执行线 | C（受全体委托） |
| 状态 | 🔄 进行中（文档已就位，共享 Schema 待重建） |
| 目标 | 以 v0.4 为准，把仓库与契约整体升级 |

**1）修改/新增的文件**

```text
仓库整体迁移     travel-planner-starter-pack-v0.3/travel-planner-starter-pack
              → travel-planner-starter-pack-v0.4          （含 .git，历史与远程保留）

新增文档         docs/SCOPE_MATRIX.md                    P0/P1 唯一裁决源
                docs/SHARED_SCHEMA_HANDOFF.md            共享模型门禁与暂停规则
                docs/DATA_PROVIDER_ARCHITECTURE.md       Mock/快照/实时/混合 Provider
                docs/PROVIDER_ASSESSMENT_TEMPLATE.md     单个 API 评估模板
                docs/CHANGELOG.md                        v0.4 修正记录
                docs/adr/0005、0006                       新增两条架构决策

新增契约材料     contracts/contract_models.py             718 行基线模型
                contracts/validate_fixtures.py            自检脚本
                fixtures/valid（6）invalid（6）business（1）

更新文档         AGENTS.md、CONTRACTS.md、README.md 在根目录；
                docs/ 下 10 份设计文档全部换成 v0.4 版
                docs/README.md 重写为 v0.4 导览

未变             docs/DATA_SOURCE_ASSESSMENT_TEMPLATE.md、MODEL_PROVIDER_AND_SECRETS.md
                docs/adr/0001–0004（与 v0.3 完全相同）
```

**2）契约层面的实质变化**

v0.4 不是小修，是重写。对代码影响最大的 13 条：

```text
1  KnowledgeCoverage → DestinationCoverageSnapshot + PlanningReadinessEvaluation
2  单一 status → PlanValidationStatus / DataAssuranceStatus / GuideLifecycleStatus / GuideReadiness
3  裸金额 → Money（amount/min/max/currency），预算必须可复算
4  字符串数组约束 → Constraint（kind/field/operator/value/source_text）
5  ResourceCandidate → 判别联合类型（VisitPlace/Lodging/Restaurant/IntercityOption/PreparationRule）
6  PlanNode/DayPlan 与 GuideNode/GuideDay 分离，禁止混用
7  Evidence → FactRecord / Evidence / PlanningFact / DataSnapshot 四层
8  新增 VersionLineage（preserved/changed/removed 节点可追踪）
9  MCP 6 个工具 → 9 个，且改名（search_resources、get_resource_facts、…）
10 REST 正式化：统一 {ok,data,warnings,error,trace_id} 信封 + 8 个错误码
11 PlanState 不再内嵌对象，只存 ID + version
12 NodeType 删除 TRANSFER；TravelMode 增加 RAIL/FLIGHT/INTERCITY_BUS
13 TripProfile 增加 timezone、duration_days、dietary/lodging/transport 偏好、作息边界
```

**3）运行的验证**

```text
cd contracts && python validate_fixtures.py
Validated 6 valid, 6 invalid, and 1 business fixtures   ← v0.4 基线自检通过
```

环境：pydantic 2.13.5 满足 v0.4 的 `pydantic>=2.12` 要求。

注意：`MODEL_REGISTRY` 只登记 10 个模型，而 `SHARED_SCHEMA_HANDOFF.md` 要求 C 交付
40+ 个对象——基线不是成品，剩余部分由 C1 补齐。

**4）仍是模拟实现的数据或依赖**

与步骤 2 相同：旅游数据全部 MOCK_ONLY；TripProfile 提取与目的地推荐仍是规则式 STUB；
会话存储仍是内存 + JSON 快照。

**5）是否影响其他成员接口**

**是（破坏性变更，已公告）**：

- `backend/app/schemas/` 将按 v0.4 重写，v0.3 对象（`KnowledgeCoverage`、
  `ResourceCandidate`、`ChangeRequest` 等）会被替换。
- A、B 在 `schema-v0.4` 冻结前必须遵守 `docs/SHARED_SCHEMA_HANDOFF.md` 的暂停规则。

**6）遗留**

- C1 共享 Schema 重建（下一步，当前唯一阻塞项）。
- `contracts/` 目录在 C1 完成后不再保留独立副本（模型并入 `backend/app/schemas/`）。
- v0.3 目录（`travel-planner-starter-pack-v0.3`）已不再使用，可由你删除。

**7）同日补充：TripProfileDraft 落地（原 Q1）**

```text
契约      CONTRACTS.md §2.3 收紧为“关键字段必填”、§2.4 TripProfileDraft、§2.5 finalize 规则
基线      contracts/contract_models.py 新增 TripProfileDraft / finalize_trip_profile /
        IncompleteProfileError，TripProfile 去掉 missing_fields
后端      backend/app/schemas/draft.py 同款实现，并从 schemas 统一导出
        backend/app/services/missing_fields.py 改为按 Draft 判定
        追问回路改走 Draft：补齐后才 finalize 出正式 TripProfile
        会话存储新增 draft 存取（快照一并持久化，兼容旧快照格式）
契约数据  fixtures/valid/trip_profile_draft_incomplete.json
        fixtures/invalid/trip_profile_missing_required_fields.json
        fixtures/business/draft_finalize_success.json
        fixtures/business/draft_finalize_failure.json
测试      contracts: 7 valid / 7 invalid / 3 business 全过
        backend:   96 passed（原 80 + 新增 Draft 契约测试 16）
```

影响：`TripProfile` 不再有 `missing_fields`；A、B 若之前引用过该字段需要改读 Draft。
`fixtures/valid/trip_profile.json` 已同步删掉该字段。

---

## 4. 契约冻结状态

| 契约对象 | 状态 | 备注 |
|---|---|---|
| 全部契约对象 | ⚠️ **v0.4 重建中** | 旧 v0.3 实现保留在 `backend/app/schemas/` 运行，待 C1 整体替换 |
| `CONTRACTS.md` | 🔒 v0.4 为准 | 唯一字段、枚举、状态和接口标准 |
| `contracts/contract_models.py` | 📦 基线 | 718 行，仅覆盖 10 个模型，由 C1 消化进 `backend/app/schemas/` |
| `fixtures/` | ✅ 可用 | 6 合法 + 6 非法 + 1 业务用例，C1 完成后并入 `backend/tests/` |

**v0.4 冻结流程**（`SHARED_SCHEMA_HANDOFF.md`）：

```text
C 实现全部共享对象 → fixtures 全过 → 可导出 OpenAPI/JSON Schema
→ 打 schema-v0.4 标签 → 视为冻结 → A/B 恢复全速开发
```

冻结后的变更规则（`CONTRACTS.md` §15）：新增可选字段可向后兼容；
删除字段、重命名字段、改变枚举必须三人确认，且先改文档再改代码。

---

## 5. 开工前共同确认事项

`TEAM_PROJECT_PLAN.md` 第 2 节要求的确认清单：

| 确认项 | 状态 | 结论 |
|---|---|---|
| 知识库数据目录和版本 | ⚠️ 待定 | 先用模拟数据，具体信息后续确认 |
| `KnowledgeCoverage` 最低规划门槛 | ⚠️ 待定 | 建议：≥8 个游玩地点、核心事实覆盖 ≥0.8、开放规则 ≥0.8、有路线数据、有住宿候选、能给出抵达方式 |
| 数据源调研任务和 Fake Provider 方案 | ⬜ | 待 A 线执行 |
| 首批住宿候选和基础餐厅范围 | ⬜ | 待 A 线执行 |
| 主 LLM Provider 已通过 POC | ⬜ | 待三人确认 |
| 地图/天气真实 API 还是模拟 | ✅ | P0 用模拟 Provider（`FakeTravelMCPClient`，全部标 MOCK_ONLY） |
| 回归测试场景集 | ⬜ | 待建立 |
| Git 仓库和各自分支 | ✅ | 已完成，见步骤 0；`main` + 三条 `feature/*` |
| `CONTRACTS.md` v0.3 冻结 | ⚠️ | 结构与枚举已实现，待补空洞 |

**验收案例（已确认）**

- 自动修复演示：**闭馆替换**（某景点当天闭馆 → 换同区域替代景点 → 重新验证）
- 突发重规划演示：**下雨**（锁定已完成/已预约节点，只重排当天剩余部分）

**技术选型（已确认）**

- P0 状态存储：**内存 + JSON 快照**，通过 Repository 接口抽象，P1 再换 MySQL
- Schema 归属：`backend/app/schemas/`，Pydantic v2

---

## 6. 联调检查表（每次联调逐条打勾）

来自 `TEAM_PROJECT_PLAN.md` 第 6 节。

| 检查项 | 负责 | 状态 |
|---|---|---|
| B 输出的 `TripProfile` 能通过 C 的 Pydantic 校验 | B/C | ⬜ |
| A 返回的候选 ID、证据 ID 在数据库中真实存在 | A | ⬜ |
| LLM 没有返回候选集合外的目的地或景点 | B | ⬜ |
| MCP 工具确实被调用，而不是只写了代码 | A/C | ⬜ |
| 不可用地点在规划前已经过滤 | C | ⬜ |
| 行程中包含移动时间和预算 | C | ⬜ |
| 验证失败不会输出 `VALIDATED` | C | ⬜ |
| 重规划没有修改锁定节点 | C | ⬜ |
| 外部 API 失败时页面仍能展示明确的降级结果 | A/B | ⬜ |
| TravelGuide 七部分存在，无法获取的字段明确标为未知 | B | ⬜ |

---

## 7. 后续步骤计划（C 线）

| 步骤 | 内容 | 结束标志 | 状态 |
|---|---|---|---|
| 1 | 骨架 + 共享 Schema v0.3 | 契约示例 JSON 全部校验通过 | ✅ |
| 2 | FastAPI + `PlanState` + LangGraph 追问回路 | 能推进到追问/推荐节点 | ✅ |
| 3 | **迁移 v0.4：文档同步 + 仓库迁移** | 以 v0.4 为准，文档与 fixtures 就位 | ✅ |
| 3.5 | **TripProfileDraft 契约补全（原 Q1）** | Draft/正式画像/finalize 与 4 个 fixture 全过 | ✅ |
| 4 | **重建共享 Schema v0.4（C1）** | fixtures 全过 + 打 `schema-v0.4` 标签 | 🔄 下一步（阻塞 A/B） |
| 5 | 前置过滤（C3） | 不可用地点不会进入规划 | ⬜ |
| 6 | 行程生成（C4） | 输出时间、交通、预算和节点 | ⬜ |
| 7 | 验证器（C5） | 能发现时间窗或预算冲突 | ⬜ |
| 8 | 通用重规划 + VersionLineage（C6） | 锁定节点不变、差异可追踪 | ⬜ |
| 9 | REST 接口集成（C7） | Vue 可端到端调用 | ⬜ |
| 10 | 端到端 fake 测试 + 联调准备 | 三条线用同一套 fixture 跑通 | ⬜ |

---

## 8. 风险登记

| 风险 | 当前状态 | 应对 |
|---|---|---|
| 契约枚举不全，规划规则无法确定化 | ⚠️ 已发生 | 见上文遗留问题 1，优先补 |
| 三条线各自新增临时字段 | 已用 `extra="forbid"` 自动拦截 | 由 12 个严格性测试守护 |
| 模拟数据被当成真实数据 | 已强制标记 `MOCK` + `MOCK_ONLY` | 由测试守护 |
| 外部 API 拿不到 | 未发生 | 统一 Provider 接口 + fake 实现 |
| 联调才发现字段不对齐 | 已缓解 | 共享 Schema + 共用 fixture |

---

## 9. 每日状态记录（模板，供三人自行追加）

```text
成员：
今天完成：
可以独立运行的结果：
正在阻塞的问题：
需要其他成员提供：
是否修改共享接口：否 / 是（未确认不得修改）
下一步：
```
