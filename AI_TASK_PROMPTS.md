# 三条开发线的AI启动提示词

使用方法：先让AI阅读项目启动包全部文件，再发送对应角色提示词。把方括号中的内容替换为实际信息。

## 公共启动提示词

```text
你正在参与“AI旅行决策与动态行程助手”项目。请先完整阅读仓库根目录下的AGENTS.md、CONTEXT.md、PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、DATA_REQUIREMENTS_CATALOG.md、MODEL_PROVIDER_AND_SECRETS.md、PROJECT_DESIGN.md、CONTRACTS.md以及docs/adr中的文件。

当前知识库数据目录/版本为：[待填写]
当前planning_ready目的地由KnowledgeCoverage检查结果决定，不人工写死
我的角色为：[A/B/C]

阅读后先不要写代码。请先输出：
1. 你理解的项目目标和第一版边界；
2. 我负责的模块、输入、输出和依赖；
3. 你准备新增或修改的文件；
4. 最小可运行验证方式；
5. 是否发现契约冲突。

不得自行改变CONTRACTS.md，不得让LLM编造旅游事实，不得实现本角色范围外的大规模重构。
```

## 成员A：数据、RAG与MCP

```text
你负责数据、RAG与MCP开发线。

目标：建立MySQL结构化事实、Chroma知识检索、KnowledgeCoverage检查和旅游MCP Server，使其他模块能够根据目的地、日期和偏好获得符合ResourceCandidate契约的候选、可用性和证据。

优先完成：
1. MySQL最小表结构和试点数据导入；
2. 认知卡片写入Chroma，元数据包含entity_id和evidence_id；
3. search_travel_knowledge、get_place_facts、get_place_availability三个MCP工具；
4. 地图/天气Provider接口及fake实现；
5. 按TRAVEL_GUIDE_SPEC收集游玩地点、住宿候选、基础餐厅、抵达方式和准备规则；
6. 输出数据源可行性表，使用UNASSESSED/AVAILABLE/LIMITED/UNAVAILABLE/MOCK_ONLY标记；
7. 正常、过期、未知三类测试数据。

不要负责TripProfile解析、Vue页面或行程排程。对未完成的外部API使用符合契约的fake provider。
```

## 成员B：LLM决策与Vue前端

```text
你负责LLM决策和Vue前端开发线。

目标：把非固定格式的用户输入转为TripProfile，识别关键缺失字段，只基于A提供的planning_ready候选、结构化事实和RAG证据进行目的地决策，并在Vue页面展示对话、候选和最终TravelGuide。

优先完成：
1. Vue 3 + Vite + Element Plus基础页面；
2. TripProfile结构化输出和Pydantic失败处理；
3. 缺失字段追问策略；
4. 目的地推荐Prompt，强制只返回planning_ready候选ID、coverage_version和evidence_ids；
5. 单目的地天数建议，并保持输出结构可扩展到双目的地；
6. 修改意图转为结构化ChangeRequest；
7. 实现GuideComposer，将TripProfile、推荐结果、验证后的ItineraryPlan和Evidence组装为七部分TravelGuide；
8. 使用fixture展示完整攻略、每日时间轴、预算和警告。

不要自行查询或编造开放时间，不要实现规划器，不要修改共享Schema。
```

## 成员C：LangGraph、规划与验证

```text
你负责LangGraph、规划、验证和FastAPI集成开发线。

目标：将TripProfile和ResourceCandidate转为经过验证的ItineraryPlan，并支持验证失败修复和用户修改后的局部重规划。

优先完成：
1. PlanState及LangGraph节点和条件边；
2. AVAILABLE/CONDITIONAL/UNAVAILABLE/UNKNOWN前置过滤；
3. 使用TripSegment数组但P0只实现一个目的地，避免未来多目的地时破坏性重构；
4. 简单可靠的每日排程，在一个目的地内安排多个游玩地点，并显式插入交通、用餐和休息；
5. 时间窗、总天数、预算和锁定节点验证；
6. 至少三种修复规则：闭馆替换、时间重排、预算无解请求用户；
7. FastAPI消息、确认、修改和突发情况接口；
8. 使用fake数据完成端到端测试。

不要自由修改A和B的模块。规划算法先追求可解释和稳定，不必追求数学最优。
```

## 集成检查提示词

```text
请作为集成审查者，阅读AGENTS.md、CONTEXT.md、PROJECT_OVERVIEW.md、TRAVEL_GUIDE_SPEC.md、PROJECT_DESIGN.md和CONTRACTS.md，然后检查当前代码是否满足：
1. 三个模块是否使用同一套Schema；
2. LLM是否可能输出不存在的实体ID或无来源事实；
3. MCP工具是否真的被LangGraph节点调用；
4. RAG结果是否保留evidence_id；
5. 前置过滤、增量检查和最终验证是否都存在；
6. 验证失败是否可能错误输出VALIDATED；
7. 局部重规划是否保留locked节点；
8. 外部API失败时是否有降级路径。
9. 用户侧最终结果是否是七部分TravelGuide，而不是只返回ItineraryPlan。

先给出按严重程度排序的问题清单，不要直接重写整个项目。
```
