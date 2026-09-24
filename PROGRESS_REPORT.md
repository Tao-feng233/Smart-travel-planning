# 项目进度报告（三人协作版）

> 本文件是三条开发线的**共享进度台账**。每完成一步就在这里追加一条记录，
> 不删除历史记录；有变更就新增一条并在末尾说明覆盖了什么。

最后更新：2026-09-24

---

## ⚡ 最新变更（只看这一块就够）

**本次更新**：2026-09-24 · 步骤 2 完成 —— FastAPI + LangGraph 追问回路可运行

**仓库地址**：https://github.com/Tao-feng233/Smart-travel-planning

**当前能跑起来的东西**

```powershell
cd backend
python -m uvicorn app.main:app --reload     # API 文档：http://127.0.0.1:8000/docs
python -m pytest                            # 80 个测试
```

第一轮消息 → 缺信息就追问；补充信息 → 推进到目的地推荐（当前用模拟数据）。

**本次结论**：C2 完成。追问回路 + 目的地推荐回路可端到端运行，缺口是 LLM 与真实数据。

**需要 A 行动**

- [ ] 确认 MCP 工具口径：`CONTRACTS.md` 列 6 个，`AI_TASK_PROMPTS.md` 只写 3 个，需要定一个
- [ ] 确认 `ResourceCandidate` / `availability` 的字段是否够 A 线交付（尤其 `CONDITIONAL` 的判定依据）
- [ ] 真实 MCP Server 请实现 `backend/app/services/travel_mcp_client.py` 里的 `TravelMCPClient` 六个方法签名，C 线按此对接

**需要 B 行动**

- [ ] 确认 `pace`、`interests[]`、`avoidances[]` 等字段的取值集合；确认前暂时按字符串处理
- [ ] 把 `backend/app/schemas/` 作为唯一 Schema 来源，不要在自己的目录复制一份
- [ ] 你的 TripProfile 提取（B2）请替换 `backend/app/services/request_parser.py`，
      行为基准见 `backend/tests/test_request_parser.py`（14 个用例）
- [ ] 你的目的地推荐（B4）请替换 `backend/app/services/destination_recommender.py`

**需要三人共同确认**

- [ ] `docs/contract-open-questions.md` 第 1 节列出的 9 个字段取值集合（`pace`、`physical_intensity`、`Conflict.type`、`RepairOption.action`、`PlanState.stage` 等）
- [ ] **`TripProfile` 允许部分字段为空**（C 线已按此实现，否则"追问"无法进行，详见待确认清单第 4 节）
- [ ] `PlanState.stage` 的取值集合采用 C 线在 `backend/app/graph/stages.py` 定义的 11 个阶段名

**已完成，不需要行动**

- 仓库与分支已建好（地址与分支见上方表格）
- 仓库已整理：根目录 `README.md` 改为项目入口（含仓库结构图与文档索引）；
  你们的原始需求文档已归到 `docs/requirements/`，并附"需求 → 设计"对应表

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

本目录（含 `AGENTS.md`、`CONTRACTS.md`）即为**代码仓库根目录**。
三条线各自的代码目录见下方“当前总览”。

---

## 1. 当前总览

| 模块 | 负责 | 目录 | 状态 | 最后更新 |
|---|---|---|---|---|
| 共享 Schema（C1） | C | `backend/app/schemas/` | ✅ 完成 | 2026-09-24 |
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
| 数据源可行性表（A6） | A | `DATA_SOURCE_ASSESSMENT_TEMPLATE.md` | ⬜ 未开始 | — |
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

---

## 4. 契约冻结状态

| 契约对象 | 状态 | 备注 |
|---|---|---|
| `TripProfile` | ⚠️ 已实现待确认 | 除 `session_id` 外允许为空，以支持"追问"（见遗留问题 11）；`pace` 等枚举待补 |
| `ResourceCandidate` | 🔒 已冻结 | 可用性四态已实现 |
| `Evidence` | 🔒 已冻结 | `REJECTED` 被强制拦截 |
| `ItineraryPlan` | 🔒 已冻结 | P0 单分段 |
| `TravelGuide` | 🔒 已冻结 | 七部分完整 |
| `PlanState` | 🔒 已冻结 | `{}` 语义用 `null` 表达 |
| MCP 工具 I/O | ⚠️ 待确认 | 部分嵌套结构为推断值 |

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
| 1 | 骨架 + 共享 Schema（C1） | 契约示例 JSON 全部校验通过 | ✅ |
| 2 | FastAPI 空壳 + `PlanState` + LangGraph 状态图（C2） | 能推进到追问/推荐/规划节点 | ✅ |
| 3 | 前置过滤（C3） | 不可用地点不会进入规划 | ⬜ |
| 4 | 行程生成（C4） | 输出时间、交通、预算和节点 | ⬜ |
| 5 | 验证器（C5） | 能发现时间窗或预算冲突 | ⬜ |
| 6 | 修复与局部重规划（C6） | 修复后重新验证，锁定节点不变 | ⬜ |
| 7 | REST 接口集成（C7） | Vue 可端到端调用 | ⬜ |
| 8 | 端到端 fake 测试 + 联调准备 | 三条线用同一套 fixture 跑通 | ⬜ |

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
