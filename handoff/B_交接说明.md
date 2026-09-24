# 给成员 B 的交接说明

> 用法：先 clone 仓库并切到你的分支，再把「提示词」整段复制给你电脑上的 AI 助手。

```bash
git clone https://github.com/Tao-feng233/Smart-travel-planning
cd Smart-travel-planning
git checkout feature/llm-vue
```

如果 clone 连不上 github.com（国内网络常见），加代理参数：
`git -c http.proxy=http://127.0.0.1:7897 clone https://github.com/Tao-feng233/Smart-travel-planning`

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
| B5 | 修改意图识别 | 输出 v0.4 的 `UserAction`（不再是 v0.3 的 `ChangeRequest`），能识别删除、替换、减轻强度等意图 |
| B6 | 攻略组装 | 把内部 `PlanNode`/`DayPlan` **富化**为 `GuideNode`/`GuideDay` 与七部分 `TravelGuide`（两类对象禁止混用） |
| B7 | 前端联调 | 可推进会话并展示完整攻略和冲突 |

---

## 项目当前状态（你开工前必须知道）

**⚠️ 最重要的变化：项目已升级到启动包 v0.4**

- 契约从 v0.3 重写为 **v0.4**：`CONTRACTS.md`（根目录）、`fixtures/`（契约测试数据）、
  `contracts/`（基线模型）。
- `PlanNode`/`DayPlan`（内部）与 `GuideNode`/`GuideDay`（用户展示）**正式分离**，
  你的 B6 就是"把内部对象富化为展示对象"，不能混用。
- 金额统一用 `Money`（含 amount / min_amount / max_amount / currency），
  约束统一用 `Constraint` 对象，不再是字符串数组。
- 修改意图的载体从 `ChangeRequest` 改为 **`UserAction`**。
- 前端拿到的 JSON 结构以 `fixtures/valid/travel_guide.json` 为准。

**⛔ 你现在必须先遵守的暂停规则**（`docs/SHARED_SCHEMA_HANDOFF.md`）

C 正在把 v0.4 契约实现成 `backend/app/schemas/`，**在此之前**：

- 不要自己定义共享对象，不要用 `dict` 临时顶替，不要在前端复制一份 `TripProfile` 结构；
- 需要但还没有的对象，发 `SCHEMA_BLOCKER` 消息（模板见该文档第 5 节）并暂停该部分；
- **可以继续做**：Vue 项目骨架、页面布局与样式、路由、组件拆分、
  不依赖共享 Schema 的前端内部类型与单元测试。

**已经做完的**

- 仓库骨架已建立：`backend/app/{api,graph,schemas,services}`。
- **共享 Schema 已有 v0.3 版本**（`backend/app/schemas/`，81 个导出对象），
  正在按 v0.4 整体重写；重写前不要依赖它的字段名。
- **契约示例数据已备好**：`fixtures/valid/travel_guide.json` 是一份完整的
  七部分攻略样例，`fixtures/valid/itinerary_plan.json` 是一份完整行程样例，
  可以直接拿来渲染页面。
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
项目目录已经同步到本机，请先完整阅读：
仓库根目录的 AGENTS.md、CONTRACTS.md（v0.4）、PROGRESS_REPORT.md；
docs/ 下的 SCOPE_MATRIX.md、SHARED_SCHEMA_HANDOFF.md、CONTEXT.md、
PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、PROJECT_DESIGN.md、
AI_TASK_PROMPTS.md、contract-open-questions.md、requirements/README.md，
以及 docs/adr/。另外要看根目录 fixtures/ 里的契约测试数据。

当前项目进度：契约已升级到 v0.4，C 正在把 v0.4 实现成 backend/app/schemas/，
尚未冻结。契约示例数据位于 fixtures/valid/，其中 travel_guide.json 是一份
完整的七部分攻略样例、itinerary_plan.json 是完整行程样例，可以用于前端渲染。
后端 API 基于 v0.3 对象，正在按 v0.4 重写。

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

共享对象一律从 backend/app/schemas/ 导入。如果需要的对象还没实现，
不要自己定义、也不要用 dict 顶替，按 docs/SHARED_SCHEMA_HANDOFF.md 第 5 节的
模板输出 SCHEMA_BLOCKER 并暂停该部分，改做页面骨架等不依赖它的工作。
```

---

## 完成后怎么同步

在自己的分支上提交，然后更新 `PROGRESS_REPORT.md` 第 1 节总览中属于你的行，
并在第 3 节追加一条步骤记录（格式：改了哪些文件、实现了哪个业务流程、
用了哪些契约、跑了哪些测试、哪些还是模拟数据、是否影响他人接口）。
