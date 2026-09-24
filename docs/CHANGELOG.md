# 变更记录

## v0.4

- 建立`SCOPE_MATRIX.md`作为P0/P1唯一范围。
- `CONTRACTS.md`重写为可执行唯一契约。
- 内部`PlanNode/DayPlan`与用户`GuideNode/GuideDay`分离。
- 普通交通统一使用`TravelLeg`，删除TRANSFER节点歧义。
- `DestinationCoverageSnapshot`与`PlanningReadinessEvaluation`分离。
- 计划可行性、数据可信度和攻略生命周期分离。
- 增加`Money`、`CostItem`和可复算`BudgetSummary`。
- 明确日期、时区、入住和退房语义。
- 正式定义`FactRecord`、`Evidence`、`PlanningFact`和`DataSnapshot`。
- 增加计划/攻略版本谱系、稳定节点ID和幂等动作。
- 补齐目的地、资源、事实、城际交通、路线、天气和准备规则等9个MCP工具。
- 增加Mock/Snapshot/Live/Hybrid可替换Provider架构。
- 统一团队目录所有权和MCP验收口径。
- 增加可运行Pydantic模型及合法、非法和业务fixtures。

## v0.3

- 最终产物统一为七部分TravelGuide。
- 明确LLM不是旅游事实来源。
- 增加KnowledgeCoverage、完整数据目录和数据调研任务说明。

