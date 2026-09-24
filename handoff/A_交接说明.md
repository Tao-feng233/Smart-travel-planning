# 给成员 A 的交接说明

> 用法：先 clone 仓库并切到你的分支，再把「提示词」整段复制给你电脑上的 AI 助手。

```bash
git clone https://github.com/Tao-feng233/Smart-travel-planning
cd Smart-travel-planning
git checkout feature/data-rag-mcp
```

如果 clone 连不上 github.com（国内网络常见），加代理参数：
`git -c http.proxy=http://127.0.0.1:7897 clone https://github.com/Tao-feng233/Smart-travel-planning`

生成日期：2026-09-24　对应项目步骤：步骤 1 完成（C 线共享 Schema 已冻结）

---

## 你的角色

**成员 A：数据、RAG 与 MCP**

交付边界一句话：*给定目的地、日期和偏好，返回符合 `ResourceCandidate` 契约的候选、可用性和证据。*

你不负责：Vue 页面、`TripProfile` 解析、目的地推荐、行程排程。

分支：`feature/data-rag-mcp`

---

## 你需要完成的任务

| 编号 | 任务 | 结束标志 |
|---|---|---|
| A1 | 设计数据表并导入试点数据 | 能查出目的地、景点和开放规则 |
| A2 | 建立认知卡片（Chroma + 索引脚本） | 查询返回内容、`entity_id`、`evidence_id` |
| A3 | 完成 RAG 检索服务 | 能按省份、目的地和类型过滤 |
| A4 | 实现 MCP 工具 | **9 个契约工具**均有可调用实现（允许 Mock） |
| A5 | 提供 Provider | Mock / Snapshot / Live / Hybrid 四种实现，同一套测试可对它们运行 |
| A6 | 填写数据源可行性表 | 明确 `AVAILABLE/LIMITED/MOCK_ONLY` 等状态 |
| A7 | 提供测试 Fixture | 正常、过期、未知三类数据 |

---

## 项目当前状态（你开工前必须知道）

**⚠️ 最重要的变化：项目已升级到启动包 v0.4**

- 契约从 v0.3 重写为 **v0.4**：`CONTRACTS.md`（根目录）、`fixtures/`（契约测试数据）、
  `contracts/`（基线模型）。
- MCP 工具从 6 个定为 **9 个**，并且改名：
  `search_planning_ready_destinations`、`search_travel_knowledge`、`search_resources`、
  `get_resource_facts`、`get_resource_availability`、`get_intercity_options`、
  `get_route`、`get_weather`、`get_preparation_rules`。
- 数据层要按 `docs/DATA_PROVIDER_ARCHITECTURE.md` 分成
  **Mock / Snapshot / Live / Hybrid** 四种可替换 Provider，业务代码不得直接依赖第三方 SDK。

**✅ 共享 Schema 已冻结，你现在可以直接开工**（标签 `schema-v0.4`）

```python
from app.schemas import (          # 这就是契约 v0.4
    TripProfile, TripProfileDraft, DestinationCoverageSnapshot,
    PlanningReadinessEvaluation, ResourceCandidateUnion, ResourceCandidateBase,
    VisitPlaceCandidate, LodgingCandidate, RestaurantCandidate, LodgingAreaCandidate,
    FactRecord, Evidence, PlanningFact, DataSnapshot,
    MCP_TOOL_MODELS,               # 9 个工具的 Request/Response
)
```

规则仍然有效（`docs/SHARED_SCHEMA_HANDOFF.md` 第 4 节）：**需要但还没有的对象，
发 `SCHEMA_BLOCKER` 并暂停该部分，不要自己定义或用 `dict` 顶替。**

两条与你直接相关的口径：

- 资源候选以 `resource_type` 判别；四类成员统一用 `resource_id` / `destination_id`。
  **外部数据的 `hotel_id` / `lodging_id` 由你在 Provider 层归一化成 `resource_id`。**
- 数据层按 `docs/DATA_PROVIDER_ARCHITECTURE.md` 分 Mock / Snapshot / Live / Hybrid，
  业务代码不得直接依赖第三方 SDK。

**已经做完的**

- 仓库骨架已建立：`backend/app/{api,graph,schemas,services}`。
- **共享 Schema v0.4 已冻结**：`backend/app/schemas/`，50 个模型 + 9 个 MCP 工具 + REST 全套。
- **契约测试数据已备好**：`fixtures/valid`（7）、`fixtures/invalid`（7）、`fixtures/business`（3），
  已接进 pytest，你自己也可以照着加。
- C 线后端已有可运行的会话/追问/推荐回路（`backend/`，112 个测试通过），可作为接口参考。
- 密钥模板在根目录 `.env.example`，`.env` 已被 `.gitignore` 忽略。

**还没做的（也就是你要做的）**

- MySQL 表、Chroma 索引、真实 MCP Server、地图/天气 Provider 全部未开始。
- 仓库根目录 `fixtures/` 里的数据**全部是模拟数据**，
  来源标记为 `source_type=MOCK` + `acquisition_status=MOCK_ONLY`，等你用真实数据替换。
- 试点目的地暂用 `dest_chengdu`（成都）占位，具体目的地清单待定。

**可以直接 import 的东西**

```python
from app.schemas import (
    ResourceCandidate, ResourceAvailability, Evidence, KnowledgeCoverage,
    SearchTravelKnowledgeInput, SearchTravelKnowledgeOutput,
    GetPlaceFactsInput, GetPlaceFactsOutput,
    GetPlaceAvailabilityInput, GetPlaceAvailabilityOutput,
    GetRouteInput, GetRouteOutput, GetWeatherInput, GetWeatherOutput,
    SearchPlanningReadyDestinationsInput, SearchPlanningReadyDestinationsOutput,
)
```

⚠️ **不要修改 `backend/app/schemas/`**。它是三条线唯一的数据对象定义处，
需要改字段时先找 C 和 B 确认，改 `CONTRACTS.md` 后再改代码。
你也**不要在自己的目录里复制一份 Schema**。

---

## 开工前需要你确认的事（2026-09-24 更新）

1. ~~MCP 工具到底做几个~~ → **已定案：9 个**，见 `CONTRACTS.md` §12，
   `backend/app/services/v04_mock_provider.py` 里有一份可运行的模拟实现可对照。
2. ~~`ResourceCandidate` 的字段够不够用~~ → **已定案**：四个成员统一继承
   `ResourceCandidateBase`（`resource_id` / `destination_id` / `resource_type`），
   见 `CONTRACTS.md` §5.2 与 `docs/contract-open-questions.md` Q4。
3. **仍然需要你确认的**：`CONDITIONAL`（有条件可用）在你的数据源里
   用什么判定依据（预约？天气？）——C3 前置过滤会据此把资源降级为"非无条件主方案"。

---

## 提示词（整段复制给 AI 助手）

```text
你正在参与“AI旅行决策与动态行程助手”项目，我在团队中担任成员 A：数据、RAG 与 MCP。
项目目录已经同步到本机，请先完整阅读：
仓库根目录的 AGENTS.md、CONTRACTS.md（v0.4）、PROGRESS_REPORT.md；
docs/ 下的 SCOPE_MATRIX.md、SHARED_SCHEMA_HANDOFF.md、DATA_PROVIDER_ARCHITECTURE.md、
CONTEXT.md、PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、DATA_REQUIREMENTS_CATALOG.md、
MODEL_PROVIDER_AND_SECRETS.md、PROJECT_DESIGN.md、AI_TASK_PROMPTS.md、
PROVIDER_ASSESSMENT_TEMPLATE.md、contract-open-questions.md、
requirements/README.md，以及 docs/adr/。
另外要看根目录 fixtures/ 里的契约测试数据。

当前项目进度：C 线已完成共享 Schema，位于 backend/app/schemas/，已冻结；
契约示例数据位于仓库根目录 fixtures/。
三条线共用同一套 Schema，我只能 from app.schemas import，不得复制定义或新增字段。

我的交付边界：给定目的地、日期和偏好，返回符合 ResourceCandidate 契约的
候选、可用性和证据。我不负责 Vue 页面、TripProfile 解析和行程排程。

我要按顺序完成：A1 MySQL 表与试点数据、A2 Chroma 认知卡片、
A3 RAG 检索、A4 MCP Server、A5 地图/天气 Provider、
A6 数据源可行性表、A7 测试 Fixture。

请先不要写代码，先输出：
1. 你理解的项目目标与第一版边界；
2. 我负责的模块、输入、输出和依赖；
3. 你准备新增或修改的文件清单（不得修改 backend/app/schemas/）；
4. 最小可运行验证方式；
5. 你发现的契约冲突或字段缺口。

约束：不得自行修改 CONTRACTS.md；不得让 LLM 编造旅游事实；
未完成的外部 API 一律提供符合契约的 fake 实现并标记 MOCK_ONLY；
不要实现本角色范围外的功能。

共享对象一律从 backend/app/schemas/ 导入。如果需要的对象还没实现，
不要自己定义、也不要用 dict 顶替，按 docs/SHARED_SCHEMA_HANDOFF.md 第 5 节的
模板输出 SCHEMA_BLOCKER 并暂停该部分，改做其他不依赖它的工作。
```

---

## 完成后怎么同步

在自己的分支上提交，然后更新 `PROGRESS_REPORT.md` 第 1 节总览中属于你的行，
并在第 3 节追加一条步骤记录（格式：改了哪些文件、实现了哪个业务流程、
用了哪些契约、跑了哪些测试、哪些还是模拟数据、是否影响他人接口）。

---

## 追加说明（2026-09-24 步骤 5：C 线代码已整体迁到 v0.4）

C 把三条线的公共代码全部换成 v0.4 对象，**v0.3 旧对象已删除**。开工前请注意：

```text
1. `app.schemas.legacy` 已经不存在；请只 from app.schemas import ...
2. REST 响应统一成信封：{ok, data, warnings, error, trace_id}
3. POST /api/sessions 的请求体必须带 run_mode（DEMO / VERIFIED）
4. v0.4 模型目前【不会】拒绝契约之外的字段（v0.3 会拒绝）。
   已登记 Q5（docs/contract-open-questions.md 5.3），三人拍板前
   不要往契约对象里加自定义字段，也不要依赖"多传会被拒绝"这条保护。
5. 你要替换的唯一入口：backend/app/services/v04_mock_provider.py
   （V04MockMCPProvider 实现 CONTRACTS.md §12 的 9 个工具；
   外部 hotel_id / lodging_id 请在 Provider 层归一化成 resource_id，见 Q4）
```

你在自己的分支写代码时，直接用 `from app.schemas import ...` 导入 Request/Response
对象构造返回值，C 的图会直接调用这些方法，签名不一致会立刻报错。
