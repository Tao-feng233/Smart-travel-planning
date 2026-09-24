# docs/ 目录导览

本目录放**查阅型资料**。根目录只保留每天都要动的那几份
（`README.md`、`AGENTS.md`、`CONTRACTS.md`、`PROGRESS_REPORT.md`），
其余文档都收在这里，避免根目录堆叠。

契约基线与契约测试数据不在本目录：见根目录的 `contracts/` 与 `fixtures/`。

## 第一次接触项目，按这个顺序读

| 顺序 | 文件 | 解决什么问题 |
|---|---|---|
| 1 | `SCOPE_MATRIX.md` | **P0/P1 的唯一裁决源**，先知道第一版到底做什么 |
| 2 | `PROJECT_OVERVIEW.md` | 项目是什么、业务流程长什么样 |
| 3 | `CONTEXT.md` | 统一术语，避免三个人说不同的词 |
| 4 | `PROJECT_DESIGN.md` | 范围边界、技术架构、三人分工 |
| 5 | `TRAVEL_GUIDE_SPEC.md` | 最终交付物（七部分攻略）包含什么 |

然后读根目录的 `CONTRACTS.md`（v0.4），再读 `SHARED_SCHEMA_HANDOFF.md`。

## 按用途分类

| 类别 | 文件 | 谁经常看 |
|---|---|---|
| 功能范围（唯一裁决源） | `SCOPE_MATRIX.md` | 三个人 |
| 契约交接与门禁 ⚠️ | `SHARED_SCHEMA_HANDOFF.md` | 三个人（**A/B 开工前必读**） |
| 契约待确认项 ⚠️ | `contract-open-questions.md` | 三个人（**改契约前必看**） |
| 版本变更记录 | `CHANGELOG.md` | 三个人（v0.4 改了什么） |
| 架构决策记录 | `adr/`（6 条） | 三个人（想改设计时先看这里有没有结论） |
| 项目总览 / 术语 / 设计 | `PROJECT_OVERVIEW.md`、`CONTEXT.md`、`PROJECT_DESIGN.md` | 三个人 |
| 交付物规格 | `TRAVEL_GUIDE_SPEC.md` | B（组装攻略）、C（生成行程） |
| 数据字段全集 | `DATA_REQUIREMENTS_CATALOG.md` | A |
| 数据 Provider 架构 | `DATA_PROVIDER_ARCHITECTURE.md` | A（Mock/快照/实时/混合） |
| 数据源可行性表（待填） | `DATA_SOURCE_ASSESSMENT_TEMPLATE.md` | A |
| 单个 API 评估模板 | `PROVIDER_ASSESSMENT_TEMPLATE.md` | A |
| 数据调研任务说明 | `DATA_RESEARCH_TASK_BRIEF.md` | A（可整份复制给独立调研任务） |
| 模型与密钥规则 | `MODEL_PROVIDER_AND_SECRETS.md` | 三个人（配 LLM 时） |
| 三人执行计划 | `TEAM_PROJECT_PLAN.md` | 三个人（任务、依赖、联调、演示） |
| AI 启动提示词 | `AI_TASK_PROMPTS.md` | 每个人开新 AI 会话时 |
| 原始需求与对应表 | `requirements/` | 三个人（讨论"这功能要不要做"时） |

## 几条约定

- 本目录文档里出现的文件名（如"见 `CONTRACTS.md`"）一律指仓库内的同名文件：
  大部分就在本目录，`CONTRACTS.md` 在仓库根目录。
- **`CONTRACTS.md` 在根目录**，且任何改动都要三人确认。
- `SCOPE_MATRIX.md` 是功能优先级的唯一来源，其他文档不得重新定义 P0/P1。
- 改文档后请同步更新 `PROGRESS_REPORT.md` 的「最新变更」，让另外两人知道。
