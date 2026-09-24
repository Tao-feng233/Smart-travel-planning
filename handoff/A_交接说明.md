# 给成员 A 的交接说明

> 用法：把「提示词」整段复制给你电脑上的 AI 助手。前提是
> `travel-planner-starter-pack` 整个目录已经同步到你的电脑。

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
| A4 | 实现 MCP 工具 | 至少 3 个工具可独立调用 |
| A5 | 提供地图/天气 Provider | 接口失败时可切换 fake 数据 |
| A6 | 填写数据源可行性表 | 明确 `AVAILABLE/LIMITED/MOCK_ONLY` 等状态 |
| A7 | 提供测试 Fixture | 正常、过期、未知三类数据 |

---

## 项目当前状态（你开工前必须知道）

**已经做完的**

- 仓库骨架已建立：`backend/app/{api,graph,schemas,services}`。
- **共享 Schema 已冻结**，位于 `backend/app/schemas/`，共 81 个导出对象。
  包含 `ResourceCandidate`、`Evidence`、`KnowledgeCoverage`、
  `DestinationRecommendation` 和 6 个 MCP 工具的输入输出模型。
- **契约示例数据已备好**，位于 `backend/tests/fixtures/`，
  可以直接当你的开发/测试数据源。
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
项目目录已经同步到本机，请先完整阅读仓库根目录下的
AGENTS.md、CONTEXT.md、PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、
DATA_REQUIREMENTS_CATALOG.md、MODEL_PROVIDER_AND_SECRETS.md、
PROJECT_DESIGN.md、CONTRACTS.md、AI_TASK_PROMPTS.md、PROGRESS_REPORT.md，
以及 docs/adr/ 和 docs/contract-open-questions.md。

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
```

---

## 完成后怎么同步

在自己的分支上提交，然后更新 `PROGRESS_REPORT.md` 第 1 节总览中属于你的行，
并在第 3 节追加一条步骤记录（格式：改了哪些文件、实现了哪个业务流程、
用了哪些契约、跑了哪些测试、哪些还是模拟数据、是否影响他人接口）。
