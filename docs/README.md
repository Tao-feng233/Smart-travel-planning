# docs/ 目录导览

本目录放**查阅型资料**。根目录只保留每天都要动的那几份
（`README.md`、`AGENTS.md`、`CONTRACTS.md`、`PROGRESS_REPORT.md`），
其余文档都收在这里，避免根目录堆叠。

## 第一次接触项目，按这个顺序读

| 顺序 | 文件 | 解决什么问题 |
|---|---|---|
| 1 | `PROJECT_OVERVIEW.md` | 项目到底是什么、业务流程长什么样 |
| 2 | `CONTEXT.md` | 统一术语，避免三个人说不同的词 |
| 3 | `PROJECT_DESIGN.md` | 范围边界、技术架构、三人分工 |
| 4 | `TRAVEL_GUIDE_SPEC.md` | 最终交付物（七部分攻略）包含什么 |

## 按用途分类

| 类别 | 文件 | 谁经常看 |
|---|---|---|
| 项目总览 | `PROJECT_OVERVIEW.md` | 三个人 |
| 术语表 | `CONTEXT.md` | 三个人 |
| 系统设计与分工 | `PROJECT_DESIGN.md` | 三个人 |
| 交付物规格 | `TRAVEL_GUIDE_SPEC.md` | B（组装攻略）、C（生成行程） |
| 数据字段全集 | `DATA_REQUIREMENTS_CATALOG.md` | A |
| 数据源可行性表（待填） | `DATA_SOURCE_ASSESSMENT_TEMPLATE.md` | A |
| 数据调研任务说明 | `DATA_RESEARCH_TASK_BRIEF.md` | A（可整份复制给独立调研任务） |
| 模型与密钥规则 | `MODEL_PROVIDER_AND_SECRETS.md` | 三个人（配 LLM 时） |
| 三人执行计划 | `TEAM_PROJECT_PLAN.md` | 三个人（任务、依赖、联调、演示） |
| AI 启动提示词 | `AI_TASK_PROMPTS.md` | 每个人开新 AI 会话时 |
| 契约待确认项 ⚠️ | `contract-open-questions.md` | 三个人（**改契约前必看**） |
| 架构决策记录 | `adr/` | 三个人（想改设计时先看这里有没有结论） |
| 原始需求与对应表 | `requirements/` | 三个人（讨论"这功能要不要做"时） |

## 几条约定

- 这些文档里的文件名引用（如"见 `CONTRACTS.md`"）一律指仓库内的同名文件：
  大部分就在本目录，`CONTRACTS.md` 在仓库根目录。
- **`CONTRACTS.md` 不在本目录**，它在根目录，且任何改动都要三人确认。
- 改文档后请同步更新 `PROGRESS_REPORT.md` 的「最新变更」，让另外两人知道。
