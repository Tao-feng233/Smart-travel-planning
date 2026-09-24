# 给成员 B 的交接说明

> 用法：把「提示词」整段复制给你电脑上的 AI 助手。前提是
> `travel-planner-starter-pack` 整个目录已经同步到你的电脑。

生成日期：2026-09-24　对应项目步骤：步骤 1 完成（C 线共享 Schema 已冻结）

---

## 你的角色

**成员 B：LLM 决策与 Vue 前端**

交付边界一句话：*把用户输入变成符合契约的 `TripProfile` 或 `ChangeRequest`，
并把经过验证的 `ItineraryPlan` 组装、展示为七部分 `TravelGuide`。*

你不负责：查询或编造开放时间、实现规划器、修改共享 Schema。

分支：`feature/llm-vue`

---

## 你需要完成的任务

| 编号 | 任务 | 结束标志 |
|---|---|---|
| B1 | 搭建 Vue 项目 | 能使用 fixture 展示结果 |
| B2 | 提取 `TripProfile` | 非固定输入能生成合法 JSON |
| B3 | 主动追问 | 缺日期/预算等会继续询问 |
| B4 | 目的地推荐 | 只返回候选 ID 并解释取舍 |
| B5 | 修改意图识别 | 能识别删除、替换、减轻强度等意图 |
| B6 | 攻略组装 `TravelGuide` | 七部分数据可由固定 JSON 组装 |
| B7 | 前端联调 | 可推进会话并展示完整攻略和冲突 |

---

## 项目当前状态（你开工前必须知道）

**已经做完的**

- 仓库骨架已建立：`backend/app/{api,graph,schemas,services}`。
- **共享 Schema 已冻结**，位于 `backend/app/schemas/`，共 81 个导出对象。
  你要用的 `TripProfile`、`TravelGuide`（七部分）、`ChangeRequestPayload`、
  `DestinationRecommendation` 都已实现。
- **契约示例数据已备好**，位于 `backend/tests/fixtures/`，
  其中 `travel_guide.json` 是一份完整的七部分攻略样例，
  `itinerary_plan.json` 是一份完整行程样例，可以直接拿来渲染页面。
- 根目录有 `.gitignore` 和 `.env.example`（前端不得持有任何服务端 API Key）。

**还没做的**

- `frontend/` 目录还不存在，Vue 项目需要你从零搭建。
- 后端 API 还没有（C 线在 C7 阶段做），所以 B7 之前请用 `backend/tests/fixtures/` 里的 JSON 做数据源。
- A 线的 RAG 接口还没有，B4 阶段先用 fixture 里的 `evidence.json` 和 `resource_candidates.json`。
- `backend/tests/fixtures/` 里的数据**全部是模拟数据**，不得当成真实旅游事实展示。

**可以直接 import / 读取的东西**

```python
from app.schemas import (
    TripProfile, DestinationRequest, DestinationRecommendation,
    TravelGuide, TripSummary, IntercityOption, PreparationItem,
    LodgingCandidate, DayPlan, PlanNode, CostItem, AlternativePlan,
    UserAction, ChangeRequestPayload, Conflict,
)
```

⚠️ **不要修改 `backend/app/schemas/`**，也不要在前端目录里复制一份 Schema 定义。
前端可以用 TypeScript 类型描述同样的结构，但结构变更必须以
`backend/app/schemas/` 和 `CONTRACTS.md` 为准。

---

## 开工前需要你确认的一件事

**`TripProfile` 里有几个字段只有示例值、没有取值集合**：

```text
pace                  示例 RELAXED，未列取值集合
interests[]           示例 FOOD / CULTURE / NATURE
avoidances[]          示例 HIGH_INTENSITY_HIKING
mobility_constraints[]、hard_constraints[]、soft_preferences[]
```

在你和三人确认之前，**这些字段按字符串处理**，不要自己发明枚举。
这件事记在 `docs/contract-open-questions.md` 第 1 节，建议你和 C、A 一起尽快定下来，
因为你的 B2 提取逻辑和 C 的规划强度校验都要用。

---

## 提示词（整段复制给 AI 助手）

```text
你正在参与“AI旅行决策与动态行程助手”项目，我在团队中担任成员 B：LLM 决策与 Vue 前端。
项目目录已经同步到本机，请先完整阅读仓库根目录下的
AGENTS.md、CONTEXT.md、PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、
DATA_REQUIREMENTS_CATALOG.md、MODEL_PROVIDER_AND_SECRETS.md、
PROJECT_DESIGN.md、CONTRACTS.md、AI_TASK_PROMPTS.md、PROGRESS_REPORT.md，
以及 docs/adr/ 和 docs/contract-open-questions.md。

当前项目进度：C 线已完成共享 Schema，位于 backend/app/schemas/，已冻结；
契约示例数据位于 backend/tests/fixtures/，其中 travel_guide.json 是
一份完整的七部分攻略样例，可以直接用于前端渲染。
后端 API 尚未实现，B7 之前请使用 fixture 作为数据源。

我的交付边界：把用户自然语言转换成符合契约的 TripProfile 或 ChangeRequest，
并把经过验证的 ItineraryPlan 组装、展示为七部分 TravelGuide。
我不负责查询或编造开放时间，不实现规划器，不修改共享 Schema。

我要按顺序完成：B1 Vue 项目、B2 TripProfile 提取、B3 主动追问、
B4 目的地推荐、B5 修改意图识别、B6 GuideComposer 攻略组装、B7 前端联调。

请先不要写代码，先输出：
1. 你理解的项目目标与第一版边界；
2. 我负责的模块、输入、输出和依赖；
3. 你准备新增或修改的文件清单（不得修改 backend/app/schemas/）；
4. 最小可运行验证方式；
5. 你发现的契约冲突或字段缺口。

约束：不得自行修改 CONTRACTS.md；不得把模型记忆当作旅游事实，
开放时间、价格、路线、住宿、餐饮和天气只能来自系统提供的数据；
只允许返回候选集合中存在的实体 ID；前端不得持有任何 API Key；
不要实现本角色范围外的功能。
```

---

## 完成后怎么同步

在自己的分支上提交，然后更新 `PROGRESS_REPORT.md` 第 1 节总览中属于你的行，
并在第 3 节追加一条步骤记录（格式：改了哪些文件、实现了哪个业务流程、
用了哪些契约、跑了哪些测试、哪些还是模拟数据、是否影响他人接口）。
