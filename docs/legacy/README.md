# 历史设计资料保留清单

本目录保留旧项目仍有参考价值的原始需求、产品规格、领域概念、数据需求、接口契约、Provider设计及架构决策。原始内容除增加历史说明外保持不变。

## 使用边界

- 原仓库使用 Vue、MySQL、Chroma、Mock/Hybrid 等方案；当前版本使用纯 JavaScript 工作台、SQLite、词法 RAG 与真实接口查询。
- 旧契约、开发分工、范围限制和完成状态仅作为历史资料，不是当前运行约束。
- 旧代码、测试结果、交接待办、旧启动说明及原 AGENTS.md 仅留在本地完整备份中，不与当前项目混用。
- 当前设计延续与尚未实现内容见 [设计思想延续](DESIGN_CONTINUITY.md)。

## 保留文档

- [共享数据与接口契约 v0.4](originals/CONTRACTS.md)
- [使用MySQL和Chroma分离事实与认知知识](originals/docs/adr/0001-mysql-and-chroma-storage.md)
- [使用受约束的LLM决策而不是纯打分或纯生成](originals/docs/adr/0002-hybrid-llm-decision.md)
- [以定制可执行旅游攻略作为最终产物](originals/docs/adr/0003-travel-guide-is-final-artifact.md)
- [LLM不是旅游事实来源](originals/docs/adr/0004-llm-is-not-a-data-source.md)
- [使用可替换的Mock、Snapshot、Live和Hybrid Provider](originals/docs/adr/0005-replaceable-data-providers.md)
- [分离计划可行性、数据可信度和攻略生命周期](originals/docs/adr/0006-separate-plan-validation-and-data-assurance.md)
- [旅行决策与行程规划领域](originals/docs/CONTEXT.md)
- [契约待确认项（由 C 线在实现共享 Schema 时登记）](originals/docs/contract-open-questions.md)
- [可替换数据Provider架构 v0.4](originals/docs/DATA_PROVIDER_ARCHITECTURE.md)
- [旅游攻略数据需求总目录 v0.1](originals/docs/DATA_REQUIREMENTS_CATALOG.md)
- [独立数据调研任务说明](originals/docs/DATA_RESEARCH_TASK_BRIEF.md)
- [数据源可行性验证表](originals/docs/DATA_SOURCE_ASSESSMENT_TEMPLATE.md)
- [模型Provider与密钥配置](originals/docs/MODEL_PROVIDER_AND_SECRETS.md)
- [项目总体设计与开发分工](originals/docs/PROJECT_DESIGN.md)
- [AI旅行决策与动态行程助手：项目全局说明书](originals/docs/PROJECT_OVERVIEW.md)
- [单个数据Provider评估模板](originals/docs/PROVIDER_ASSESSMENT_TEMPLATE.md)
- [Q6 / Q8 / Q9 决策材料（实测版）](originals/docs/Q6-Q8-Q9-决策材料.md)
- [原始需求文档（项目输入）](originals/docs/requirements/README.md)
- [旅游规划需求痛点-刘](originals/docs/requirements/旅游规划需求痛点-刘.md)
- [用户实际需求](originals/docs/requirements/需求汇总-初版.md)
- [P0/P1能力矩阵 v0.4](originals/docs/SCOPE_MATRIX.md)
- [共享Schema交接与阻塞规则](originals/docs/SHARED_SCHEMA_HANDOFF.md)
- [三人团队项目执行计划书](originals/docs/TEAM_PROJECT_PLAN.md)
- [定制可执行旅游攻略规格 v0.4](originals/docs/TRAVEL_GUIDE_SPEC.md)
