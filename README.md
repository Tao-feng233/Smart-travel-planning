# AI旅行决策与动态行程助手

仓库：`Smart-travel-planning`　契约版本：**v0.4**　三人团队项目
（A 数据/RAG/MCP　B LLM/前端　C LangGraph/规划/后端）

## 项目是什么

系统通过自然语言收集用户需求，**只从知识库数据覆盖达到规划门槛的目的地中**推荐，
把模糊的旅行想法变成一份带约束验证、可修改、可局部重规划的七部分定制攻略。

第一版强调**“覆盖范围有限、业务闭环完整”**。它不是全国旅游平台，
不负责真实支付、出票或酒店预订。

## 现在做到哪了

完整进度台账见 **[PROGRESS_REPORT.md](PROGRESS_REPORT.md)**（每完成一步追加一条记录）。

```text
步骤 0  ✅ Git 仓库与三条分支
步骤 1  ✅ 共享 Schema（v0.3 版，将被 v0.4 替换）
步骤 2  ✅ FastAPI + LangGraph 追问/推荐回路
步骤 3  🔄 迁移到 v0.4：契约重写 + 共享 Schema 重建（进行中）
```

> ✅ **共享 Schema v0.4 已交付并冻结**（标签 `schema-v0.4`）。
> A、B 现在可以全速开工：`from app.schemas import ...` 拿到的就是 v0.4 对象。
> 缺对象时仍按 [docs/SHARED_SCHEMA_HANDOFF.md](docs/SHARED_SCHEMA_HANDOFF.md)
> 第 4 节发 `SCHEMA_BLOCKER`，不要自己定义或用 `dict` 顶替。

后端当前可运行（基于 v0.3 对象，正在按 v0.4 重写）：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload   # 接口文档 http://127.0.0.1:8000/docs
python -m pytest
```

## 仓库结构

```text
Smart-travel-planning/
├── README.md                  ← 本文件
├── AGENTS.md                  AI 助手必须遵守的协作与编码规则（每次开会话必读）
├── CONTRACTS.md               ⭐ 契约 v0.4：唯一字段、枚举、状态和接口标准
├── PROGRESS_REPORT.md         ⭐ 共享进度台账（看「⚡ 最新变更」一节即可）
│
├── docs/                      查阅型资料，见 docs/README.md
│   ├── README.md                    本目录导览：什么阶段读哪份
│   ├── SCOPE_MATRIX.md              ⭐ P0/P1 唯一裁决源
│   ├── SHARED_SCHEMA_HANDOFF.md     ⭐ C 必须交付的共享模型 + A/B 暂停规则
│   ├── DATA_PROVIDER_ARCHITECTURE.md Mock/快照/实时/混合 Provider 架构
│   ├── PROVIDER_ASSESSMENT_TEMPLATE.md 单个 API 的评估模板
│   ├── CHANGELOG.md                 v0.4 相对 v0.3 的修正记录
│   ├── PROJECT_OVERVIEW.md          项目全局说明
│   ├── CONTEXT.md                   统一术语
│   ├── PROJECT_DESIGN.md            范围、架构、三人分工
│   ├── TRAVEL_GUIDE_SPEC.md         七部分攻略的内容与字段要求
│   ├── TEAM_PROJECT_PLAN.md         三人任务、依赖、联调与演示计划
│   ├── DATA_REQUIREMENTS_CATALOG.md 数据字段全集
│   ├── DATA_SOURCE_ASSESSMENT_TEMPLATE.md 数据源可行性表（A 线填写）
│   ├── DATA_RESEARCH_TASK_BRIEF.md  数据调研任务说明
│   ├── MODEL_PROVIDER_AND_SECRETS.md 模型抽象与密钥规则
│   ├── AI_TASK_PROMPTS.md           三条开发线的 AI 启动提示词
│   ├── contract-open-questions.md   契约待确认项（C 线登记）
│   ├── adr/                         架构决策记录（6 条）
│   └── requirements/                原始需求文档 + 需求→设计对应表
│
├── contracts/                 v0.4 基线：契约模型基线 + fixtures 自检脚本
│                              （C 线将把它实现进 backend/app/schemas/ 后移除）
├── fixtures/                  ⭐ v0.4 契约测试数据（valid / invalid / business）
├── handoff/                   给 A / B 的交接说明（含可直接复制的提示词）
├── backend/                   C 线后端
│   ├── app/{api,core,graph,schemas,services}/
│   └── tests/
├── frontend/                  B 线 Vue（尚未创建）
└── data/                      A 线数据与导入脚本（尚未创建）
```

根目录刻意只保留**每天都要动**的四份文件，其余文档全部收在 `docs/`。

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

开工前必看四处：

1. `PROGRESS_REPORT.md` 的「⚡ 最新变更」——**需要你做什么**；
2. [docs/SHARED_SCHEMA_HANDOFF.md](docs/SHARED_SCHEMA_HANDOFF.md)——哪些共享对象已就绪、缺了要怎么暂停；
3. [docs/SCOPE_MATRIX.md](docs/SCOPE_MATRIX.md)——P0 到底做什么；
4. [docs/contract-open-questions.md](docs/contract-open-questions.md)——契约里还没定死的地方。

> 如果 clone 时连不上 github.com（国内网络常见），加代理参数：
> `git -c http.proxy=http://127.0.0.1:7897 clone https://github.com/Tao-feng233/Smart-travel-planning`

## 文档索引

| 我想… | 看哪份 |
|---|---|
| 知道现在做到哪、下一步谁做什么 | `PROGRESS_REPORT.md` |
| 知道 P0/P1 边界 | `docs/SCOPE_MATRIX.md` |
| 知道某个字段/接口长什么样 | `CONTRACTS.md` v0.4 |
| 知道 C 要交付哪些共享模型、自己何时该暂停 | `docs/SHARED_SCHEMA_HANDOFF.md` |
| 知道数据从哪来、怎么降级 | `docs/DATA_PROVIDER_ARCHITECTURE.md`、`docs/DATA_REQUIREMENTS_CATALOG.md` |
| 第一次了解项目全貌 | `docs/README.md` → `docs/PROJECT_OVERVIEW.md` |
| 知道为什么这么设计 | `docs/PROJECT_DESIGN.md`、`docs/adr/` |
| 看用户最初提了什么需求 | `docs/requirements/` |
| 让 AI 助手开工 | `handoff/*_交接说明.md` 里的提示词 |
| v0.4 改了什么 | `docs/CHANGELOG.md` |

## 契约自检

```powershell
cd contracts
python validate_fixtures.py
```

验证 6 个合法 fixture、6 个非法 fixture 和 1 个业务用例（锁定节点不可变）。
待 C 把模型实现进 `backend/app/schemas/` 后，这套校验会并入 `backend/tests/`。

## 三人使用AI的统一方法

每位成员开启新的AI对话时：

1. 把本目录放入代码仓库根目录。
2. 要求AI依次阅读 `AGENTS.md` 中的文件清单。
3. 使用 `docs/AI_TASK_PROMPTS.md` 中对应角色的提示词。
4. 要求AI先复述自己的边界、输入、输出和依赖，再开始写代码。
5. AI不得自行修改 `CONTRACTS.md`；确需修改时，必须由三人确认后先更新文档，再改代码。

## 开始编码的最低条件

- 已导入至少一组能通过 KnowledgeCoverage / PlanningReadiness 检查的试点数据。
- 三人认可 `docs/CONTEXT.md` 中的术语。
- `CONTRACTS.md v0.4` 的 Schema 和 fixtures 通过验证。
- 每条开发线都能使用模拟数据独立运行。
- 已建立覆盖主要业务分支的回归测试场景，不要求提前固定最终演示文案。

## 推荐的三条演示场景

1. 用户不知道去哪：系统追问、RAG检索、LLM比较目的地并生成完整攻略。
2. 用户已确定一个目的地：系统生成包含抵达、准备、住宿、多个游玩地点、餐饮和交通的完整攻略。
3. 用户起晚或遇到下雨：系统锁定已完成/已预约节点，只重规划剩余部分。

双目的地真实规划为P1演示，有余力时再加入。
