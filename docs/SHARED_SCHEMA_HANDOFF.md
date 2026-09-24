# 共享Schema交接与阻塞规则

## 1. 目的

> **状态（2026-09-24）**：本文件要求的共享 Schema 已交付并冻结。
>
> ```text
> 位置      backend/app/schemas/（v0.4 实现在 backend/app/schemas/v04/）
> 内容      50 个模型 + 9 个 MCP 工具 Request/Response + REST 全套
> 验证      fixtures/valid 7 全过、fixtures/invalid 7 全失败、business 3 通过
> 冻结标签  schema-v0.4
> 用法      from app.schemas import TripProfile, ResourceCandidateUnion, ...
> ```
>
> v0.3 的旧对象（`backend/app/schemas/legacy/`）**已经删除**（2026-09-24 步骤 5）。
> 现在 `backend/app/schemas/` 只有 v0.4 一层，旧名字一律不可用。
>
> 第 4 节的暂停规则依然有效：缺对象请发 `SCHEMA_BLOCKER`，不要自己造。

`CONTRACTS.md`是纸面契约，`backend/app/schemas/`中的Pydantic模型是运行时契约。成员C负责将全部共享对象实现并导出；A、B只能引用，不能各自复制或自行补字段。

启动包中的`contracts/contract_models.py`是基线和契约测试，不代表所有生产Schema已经实现完毕。

## 2. C必须提供的共享对象

### 通用类型

```text
Money
TimeWindow
全部共享枚举
统一响应Envelope
统一Error/Warning对象
```

### 用户需求与推荐

```text
Constraint
DestinationRequest
TripProfile
DestinationCoverageSnapshot
PlanningReadinessEvaluation
DestinationRecommendation
```

### 数据、事实和证据

```text
FactRecord
Evidence
PlanningFact
DataSnapshot
```

### 资源判别联合类型

```text
ResourceCandidateBase
VisitPlaceCandidate
LodgingCandidate
RestaurantCandidate
IntercityOption
PreparationRule
ResourceCandidateUnion
```

联合类型必须使用`resource_type`作为判别字段，A不得返回无类型的任意dict。

### 行程、费用和验证

```text
TripSegment
StaySegment
PlanNode
TravelLeg
DayPlan
CostItem
BudgetSummary
ItineraryPlan
RepairOption
Conflict
AlternativePlan
```

### 用户攻略

```text
GuideNode
GuideDay
TripSummarySection
ArrivalAndDepartureSection
PreparationSection
LodgingSection
BudgetAndAlternativesSection
SourcesAndFreshnessSection
TravelGuide
```

### 状态、动作和版本

```text
PlanState
UserAction
VersionLineage
```

### MCP与REST输入输出

```text
9个MCP工具的Request/Response模型
创建会话Request/Response
消息Request/Response
确认攻略Request/Response
修改攻略Request/Response
突发情况Request/Response
刷新数据Request/Response
```

## 3. C的完成标准

- 所有对象位于`backend/app/schemas/`，通过统一`__init__.py`导出。
- 字段、枚举和不变量与`CONTRACTS.md v0.4`一致。
- 能生成OpenAPI/JSON Schema。
- `fixtures/valid`全部通过。
- `fixtures/invalid`全部按预期失败。
- A、B不需要导入C的业务服务，只导入共享Schema。
- C提交一个明确的`schema-v0.4`提交或标签后，才视为共享Schema冻结。

## 4. A、B及其AI必须暂停的情况

遇到以下任一情况，立即停止相关实现并向C或三人小组询问：

1. `CONTRACTS.md`中有对象，但`backend/app/schemas/`无法导入。
2. 需要的字段、枚举或Request/Response模型尚未定义。
3. 现有Schema无法表达当前功能。
4. 需要删除、重命名或改变共享字段含义。
5. 想用`dict[str, Any]`临时代替一个共享业务对象。
6. 想在自己的模块中复制定义`TripProfile`、`ResourceCandidate`、`ItineraryPlan`或`TravelGuide`。
7. MCP/REST请求响应与现有模型对不上。

允许继续的工作：页面布局、Provider内部实现、数据库连接、纯内部私有类型和不依赖缺失Schema的单元测试。

## 5. 阻塞消息模板

```text
SCHEMA_BLOCKER
角色：A / B
缺失或冲突对象：
CONTRACTS.md对应章节：
当前要实现的功能：
期望输入：
期望输出：
为什么现有Schema无法使用：
是否建议新增字段：否 / 是（说明理由）
受影响文件：
```

发送该消息后，AI不得自行生成替代共享Schema。若只是C尚未实现但契约已经明确，由C补代码；若契约本身有歧义，再由三人拍板。

## 6. 变更流程

```text
提出SCHEMA_BLOCKER
→ C判断是实现缺失还是契约歧义
→ 实现缺失：C按现有契约补模型和测试
→ 契约歧义：三人确认
→ 先修改CONTRACTS和fixtures
→ 再修改Pydantic模型
→ 测试通过
→ A/B更新调用
```
