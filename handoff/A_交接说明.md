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

**⛔ 你现在必须先遵守的暂停规则**（`docs/SHARED_SCHEMA_HANDOFF.md`）

C 正在把 v0.4 契约实现成 `backend/app/schemas/`，**在此之前**：

- 不要自己定义共享对象，不要用 `dict` 临时顶替，不要复制 `TripProfile` / `ResourceCandidate` 等模型；
- 需要但还没有的对象，发 `SCHEMA_BLOCKER` 消息（模板见该文档第 5 节）并暂停该部分；
- **可以继续做**：Provider 内部实现、数据库连接、Chroma 索引、数据调研（A6）、
  纯内部私有类型、不依赖缺失 Schema 的单元测试。

**已经做完的**

- 仓库骨架已建立：`backend/app/{api,graph,schemas,services}`。
- **共享 Schema 已有 v0.3 版本**（`backend/app/schemas/`，81 个导出对象），正在按 v0.4 整体重写。
- **契约测试数据已备好**：`fixtures/valid`（6）、`fixtures/invalid`（6）、`fixtures/business`（1）。
- 密钥模板在根目录 `.env.example`，`.env` 已被 `.gitignore` 忽略。

**还没做的（也就是你要做的）**

- MySQL 表、Chroma 索引、真实 MCP Server、地图/天气 Provider 全部未开始。
- `backend/tests/fixtures/` 里的数据**全部是模拟数据**，
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

## 开工前需要你确认的两件事

1. **MCP 工具到底做几个**：`CONTRACTS.md` §12 列了 6 个工具
   （`search_planning_ready_destinations`、`search_travel_knowledge`、
   `get_place_facts`、`get_place_availability`、`get_route`、`get_weather`），
   但 `AI_TASK_PROMPTS.md` 的 A 角色提示词只写了 3 个。**P0 底线是至少 3 个**。
   建议优先做这三个：`search_planning_ready_destinations`（支撑推荐）、
   `search_travel_knowledge`（支撑 RAG 证据）、`get_place_availability`（支撑闭馆过滤）。
2. **`ResourceCandidate` 的字段够不够用**：尤其 `availability.status=CONDITIONAL`
   你打算用什么判定依据（预约？天气？），以及是否需要补充字段。

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
契约示例数据位于 backend/tests/fixtures/。
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
