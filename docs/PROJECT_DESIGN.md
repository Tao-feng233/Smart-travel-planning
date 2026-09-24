# 项目总体设计与开发分工

## 1. 产品目标

面向不熟悉目的地、希望自由行但不愿花大量时间做攻略的用户，将模糊旅行需求转化为基于已有数据、经过约束验证、可以修改和局部重规划的定制可执行旅游攻略。

第一版采用有限知识库试点：只在数据覆盖通过KnowledgeCoverage检查的目的地中推荐，覆盖范围由数据决定，但完整实现需求理解、RAG检索、LLM决策、行程规划、验证和重规划。

## 2. 第一版范围

### 必须实现

- Vue对话和七部分攻略展示页面。
- 自然语言提取 `TripProfile`。
- 至少一次根据缺失字段的主动追问。
- RAG检索目的地或景点认知资料，并在LLM输出中保留证据ID。
- LLM在已通过硬条件初筛的目的地中进行主观比较和推荐。
- MCP至少提供知识检索、地点事实或路线查询工具。
- LangGraph包含追问回路和“验证失败→修复→再验证”回路。
- 根据日期、开放规则和硬约束前置过滤地点。
- 完整支持单目的地；一个目的地内规划多个游玩区域和多个游玩地点。
- 数据结构支持多个TripSegment，但P0限制为一个，双目的地实际规划暂列P1。
- 生成带多个景点、餐饮、休息、时间、交通、费用和提示的每日行程。
- 检测并修复至少一种冲突。
- 支持用户修改或突发情况后的局部重规划。
- 将验证后的行程与抵达方式、准备清单、住宿、预算、备选和来源组装为七部分TravelGuide。

### 可以简化

- 每个目的地只准备8～15个核心景点和少量餐饮候选。
- 住宿提供区域和人工整理的具体住宿候选，不声称实时可订。
- 人流只预测低、中、高等级，不预测精确人数。
- 城际交通可以使用人工维护的典型耗时和价格。
- 地图、天气接口失败时允许切换到模拟Provider。
- 突发情况重点实现下雨或用户起晚两个案例。

### 明确不做

- 全国或全球覆盖。
- 真实支付、出票、酒店预订。
- 任意数量的多城市路线优化。
- 实时客流精确人数和抢票成功率。
- 社区、评论发布、原生移动端和复杂账号体系。

## 3. 核心业务流程

```text
用户输入旅行请求
→ LLM提取TripProfile
→ 检查影响规划的缺失字段
→ 若缺失则追问并更新TripProfile
→ 从知识库获取planning_ready目的地并执行硬条件初筛
→ RAG检索目的地认知资料
→ LLM比较候选、建议目的地和停留天数
→ 用户确认目的地（P0一个，P1最多两个相邻目的地）
→ MCP获取地点事实、可用性、路线和天气
→ 前置过滤不可用地点
→ LLM对可行候选进行偏好分析
→ 生成目的地分段和每日行程
→ 规划过程中增量检查
→ 完整行程全局验证
→ 有冲突则最小范围修复并再验证
→ 组装TravelGuide并输出完整攻略、证据、风险和待办
→ 用户确认、修改或报告突发情况
→ 局部重规划
```

## 4. 技术架构

```text
Vue 3 + Vite + Element Plus
              │
              ▼
        FastAPI REST API
              │
              ▼
         LangGraph 工作流
   ┌──────────┼──────────┐
   ▼          ▼          ▼
LLM决策    规划验证器    MCP Client
   │          │          │
   └────┬─────┘          ▼
        ▼          旅游 MCP Server
    攻略组装器       ┌────┼────┐
        │            ▼    ▼    ▼
        ▼          MySQL Chroma 外部/模拟Provider
   TravelGuide   结构化事实 RAG知识 地图/天气/路线
```

### 技术选择

- 前端：Vue 3、Vite、Element Plus、Axios。
- 后端：Python、FastAPI、Pydantic。
- 工作流：LangGraph；节点保持为可独立测试的普通Python函数。
- 数据库：MySQL保存事实、用户状态和计划。
- 向量库：Chroma保存认知卡片和攻略摘要，通过实体ID关联MySQL。
- RAG：元数据过滤后向量检索，结果携带 `evidence_id`。
- MCP：统一封装知识、事实、可用性、路线和天气工具。
- 部署：优先本地运行；有余力再使用Docker Compose。

## 5. LLM与确定性程序的边界

### LLM负责

- 理解非固定格式的自然语言。
- 提取约束、偏好和修改意图。
- 判断哪些缺失条件值得追问。
- 基于RAG证据比较可行目的地。
- 对可行资源进行主观适配分析。
- 提出修复方向并解释推荐、排除和变更原因。

LLM不提供任何旅游事实。所有事实先由数据层、RAG和MCP工具进入工作流状态，LLM只读取这些上下文进行分析和决断。

### 程序、数据库或工具负责

- 支持范围判断。
- 开放日期、闭馆日、预约和最晚进入时间。
- 交通距离、耗时和费用。
- 总天数、分段天数和预算计算。
- 硬约束过滤。
- 行程衔接和冲突验证。
- 判断修复后是否真正可行。

### 推荐原则

不采用“纯打分推荐”，也不采用“纯LLM自由推荐”。正确顺序是：

```text
程序过滤不可能项
→ RAG提供可追溯资料
→ LLM进行主观比较和天数建议
→ 程序验证LLM结果
```

LLM只能返回检索候选中存在的实体ID；找不到可靠资料时必须返回资料不足。

## 6. 多目的地规划

第一版最多支持两个相邻支持目的地。

```text
总旅行天数
→ LLM根据用户表达提出目的地和天数草案
→ 程序检查各目的地最小/最大天数及移动耗时
→ 形成TripSegment
→ 分别规划每个分段内部行程
→ 插入地点间TravelLeg
→ 全局验证
```

用户说“成都多玩几天、乐山只去一天”时，系统记录成都为较高天数偏好，乐山为固定一天；如果总天数不足，必须说明冲突并要求用户选择，不得静默压缩。

## 7. 数据可靠性与更新

每条关键事实保存来源、采集时间、有效期和状态。规划时形成 `DataSnapshot`。

- 静态认知：区域特点、适合人群、典型体验。
- 半动态事实：开放时间、票价、预约规则。
- 动态数据：天气、路线、临时关闭。
- 预测数据：历史人流等级。

候选状态只能是：

- `AVAILABLE`：可以进入规划。
- `CONDITIONAL`：满足预约、天气确认等条件后可用。
- `UNAVAILABLE`：明确排除。
- `UNKNOWN`：资料不足，不得作为无条件主方案。

## 8. LangGraph节点

```text
parse_request
check_missing_fields
ask_clarification
retrieve_destinations
recommend_destinations
confirm_destinations
fetch_resources
filter_availability
build_trip_segments
build_daily_plan
validate_plan
repair_plan
assemble_travel_guide
present_plan
interpret_change
replan_affected_scope
```

主要条件边：

- 有关键字段缺失：`check_missing_fields → ask_clarification → parse_request`。
- 目的地未确认：`recommend_destinations → confirm_destinations`，等待用户输入。
- 验证失败且可自动修复：`validate_plan → repair_plan → validate_plan`。
- 验证失败且需放宽条件：返回用户选择修复选项。
- 用户修改：`interpret_change → replan_affected_scope → validate_plan`。

## 9. 三人分工

### A：数据、RAG与MCP

负责MySQL表、试点数据、来源和有效期、Chroma索引、RAG检索、MCP Server、地图/天气/模拟Provider。

交付边界：给定目的地、日期和偏好，返回符合 `ResourceCandidate` 契约的候选及证据。

### B：LLM决策与Vue前端

负责TripProfile提取、主动追问、目的地比较、多地点天数建议、修改意图、推荐解释、攻略组装器，以及Vue对话、候选和完整攻略页面。

交付边界：把用户输入变成符合契约的TripProfile或ChangeRequest，并将经过验证的ItineraryPlan组装、展示为TravelGuide。

### C：LangGraph、规划与验证

负责LangGraph状态流、可用性前置过滤、TripSegment、每日排程、预算和时间验证、冲突修复、PlanState、局部重规划、FastAPI集成。

交付边界：把TripProfile和ResourceCandidate转换成经过验证的ItineraryPlan。

## 10. 集成规则

- 三人只能通过 `CONTRACTS.md` 中的对象和接口连接。
- 开发早期全部模块必须提供模拟实现，避免等待真实API。
- 公共对象只定义一次，建议放在 `backend/app/schemas/`。
- 每条线至少提供一个不依赖其他成员的测试脚本。
- 接口修改先改契约，再改提供方和消费方。
- AI生成代码必须通过格式校验和最小测试后才能合并。

## 11. 项目完成标准

项目完成不等于所有设想全部实现，而是三条演示场景可以从Vue页面端到端运行，最终生成 `TRAVEL_GUIDE_SPEC.md` 定义的七部分TravelGuide；LLM、LangGraph、RAG和MCP都有不可替代的实际作用，关键硬约束由程序验证，数据不足时能够降级或拒绝，用户修改后能够保留锁定内容并更新受影响的攻略部分。
