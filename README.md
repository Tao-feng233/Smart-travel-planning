# AI旅行决策与动态行程助手

仓库：`Smart-travel-planning`　三人团队项目（A 数据/RAG/MCP　B LLM/前端　C LangGraph/规划/后端）

## 项目是什么

系统通过自然语言收集用户需求，**只从知识库数据覆盖达到规划门槛的目的地中**推荐，
把模糊的旅行想法变成一份带约束验证、可修改、可局部重规划的七部分定制攻略。

```text
自然语言需求 → 主动追问 → RAG检索 → LLM目的地推荐 → MCP获取事实与路线
→ LangGraph编排 → 行程生成 → 约束验证与修复 → 用户修改或突发重规划 → 七部分TravelGuide
```

第一版强调**“覆盖范围有限、业务闭环完整”**。它不是全国旅游平台，
不负责真实支付、出票或酒店预订。

## 现在做到哪了

完整进度台账见 **[PROGRESS_REPORT.md](PROGRESS_REPORT.md)**（每完成一步追加一条记录）。

```text
步骤 0  ✅ Git 仓库与三条分支
步骤 1  ✅ 共享 Schema（81 个契约对象）+ 契约示例 fixture
步骤 2  ✅ FastAPI + LangGraph 追问/推荐回路（80 个测试）
步骤 3  ⬜ 前置过滤（C3）
```

目前可以真实运行的部分：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload   # 接口文档 http://127.0.0.1:8000/docs
python -m pytest                          # 80 passed
```

```text
第 1 轮「我想出去玩，不想早起」
  → 系统追问：出发地 / 出发日期 / 返回日期 / 人数 / 预算
第 2 轮「从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文」
  → 系统从覆盖达标的目的地中推荐候选，并附上证据 ID
```

> ⚠️ 当前所有旅游数据都是**模拟数据**（标记为 `MOCK_ONLY`），仅用于跑通流程。
> A 线接入 MySQL / Chroma / 真实 MCP Server 后替换。

## 仓库结构

```text
Smart-travel-planning/
├── README.md                  本文件：项目入口
├── PROGRESS_REPORT.md         ⭐ 三人共享的进度台账（看"最新变更"一节即可）
├── CONTRACTS.md               ⭐ 模块之间唯一允许使用的数据和接口格式
├── AGENTS.md                  AI 助手必须遵守的协作与编码规则
├── CONTEXT.md                 统一术语
├── PROJECT_OVERVIEW.md        项目全局说明
├── PROJECT_DESIGN.md          产品范围、业务流程、技术架构、三人分工
├── TRAVEL_GUIDE_SPEC.md       七部分攻略的内容与字段要求
├── TEAM_PROJECT_PLAN.md       三人任务、依赖、联调与演示计划
├── DATA_REQUIREMENTS_CATALOG.md      需要收集的全部数据字段
├── DATA_SOURCE_ASSESSMENT_TEMPLATE.md 数据源可行性验证表（A 线填写）
├── DATA_RESEARCH_TASK_BRIEF.md       数据调研任务说明
├── MODEL_PROVIDER_AND_SECRETS.md     模型抽象与密钥规则
├── AI_TASK_PROMPTS.md         三条开发线的 AI 启动提示词
├── docs/
│   ├── adr/                   关键架构决定（4 条）
│   ├── contract-open-questions.md    ⚠️ 契约待确认项（改动前必看）
│   └── requirements/          原始需求文档 + 需求→设计对应表
├── handoff/                   给 A / B 的交接说明（含可直接复制的提示词）
├── backend/                   C 线后端（当前唯一有代码的目录）
│   ├── app/{api,core,graph,schemas,services}/
│   └── tests/                 80 个测试 + 契约示例 fixture
├── frontend/                  B 线 Vue（尚未创建）
└── data/                      A 线数据与导入脚本（尚未创建）
```

## 三个人各自怎么开始

```bash
git clone https://github.com/Tao-feng233/Smart-travel-planning
cd Smart-travel-planning
git checkout feature/<你的分支>
```

| 成员 | 分支 | 交接说明 |
|---|---|---|
| A 数据、RAG 与 MCP | `feature/data-rag-mcp` | [handoff/A_交接说明.md](handoff/A_交接说明.md) |
| B LLM 决策与 Vue 前端 | `feature/llm-vue` | [handoff/B_交接说明.md](handoff/B_交接说明.md) |
| C LangGraph、规划与验证 | `feature/graph-planner` | — |

开工前先看两处：

1. `PROGRESS_REPORT.md` 的「⚡ 最新变更」——里面写着**需要你做什么**；
2. [docs/contract-open-questions.md](docs/contract-open-questions.md)——契约里**还没定死**的地方。

> 如果 clone 时连不上 github.com（国内网络常见），加代理参数：
> `git -c http.proxy=http://127.0.0.1:7897 clone https://github.com/Tao-feng233/Smart-travel-planning`

## 文档索引

| 我想… | 看哪份 |
|---|---|
| 知道现在做到哪、下一步谁做什么 | `PROGRESS_REPORT.md` |
| 知道某个字段/接口长什么样 | `CONTRACTS.md`（+ `backend/app/schemas/`） |
| 知道为什么这么设计 | `PROJECT_DESIGN.md`、`docs/adr/` |
| 知道最终产物要包含什么 | `TRAVEL_GUIDE_SPEC.md` |
| 知道要收集哪些数据、从哪来 | `DATA_REQUIREMENTS_CATALOG.md`、`DATA_SOURCE_ASSESSMENT_TEMPLATE.md` |
| 看用户最初提了什么需求 | `docs/requirements/` |
| 让 AI 助手开工 | `handoff/*_交接说明.md` 里的提示词 |
