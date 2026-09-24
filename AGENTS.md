# AI协作规则

## 开始任务前

所有AI助手在分析或修改代码前必须依次阅读：

1. `docs/CONTEXT.md`
2. `docs/PROJECT_OVERVIEW.md`
3. `docs/TRAVEL_GUIDE_SPEC.md`
4. `docs/DATA_REQUIREMENTS_CATALOG.md`
5. `docs/MODEL_PROVIDER_AND_SECRETS.md`
6. `docs/PROJECT_DESIGN.md`
7. `CONTRACTS.md`
8. 与当前任务相关的 `docs/adr/`
9. `PROGRESS_REPORT.md` 的「最新变更」一节（当前进度与需要你做什么）

## 仓库文件位置约定

```text
根目录（每天都要动）      README.md / AGENTS.md / CONTRACTS.md / PROGRESS_REPORT.md
docs/                    查阅型资料：设计、规格、数据、计划、决策记录、原始需求
handoff/                 给 A / B 的交接说明与 AI 启动提示词
backend/  frontend/  data/   三条开发线的代码目录
```

文档里出现的文件名（如 `PROJECT_DESIGN.md`）一律指仓库内的同名文件，
大部分位于 `docs/`；`CONTRACTS.md`、`AGENTS.md`、`README.md`、`PROGRESS_REPORT.md` 在根目录。

阅读后先说明：当前负责模块、输入契约、输出契约、依赖模块和不在本次范围内的内容。

## 不可违反的项目原则

- 项目按知识库实际覆盖范围运行，只推荐 `planning_ready=true` 的目的地，不使用人工硬编码名单。
- LLM不是旅游事实来源；不得把自身记忆当作目的地、开放时间、价格、路线、住宿、餐饮或天气信息。
- LLM只能基于MySQL事实、MCP工具结果和RAG证据进行分析、比较和解释。
- 事实来自MySQL、MCP工具或带来源的数据Provider；认知文本来自RAG。
- LLM只能选择候选集合中存在的实体ID。
- RAG或事实工具返回为空时必须返回资料不足，不得回退到模型记忆。
- 所有推荐理由中的可核验事实必须能关联entity_id或evidence_id。
- 固定事实和未获授权的可协商硬约束不得被自动突破。
- `UNAVAILABLE`资源不得进入计划；`UNKNOWN`资源不得成为无条件主方案。
- 规划前要过滤，规划中要增量检查，规划后要全局验证。
- 验证失败不能把计划标为 `VALIDATED`。
- 局部重规划必须保留锁定节点和无关安排。
- 数据不足、接口失败或条件无解时要明确降级或返回用户选择，不得伪造。
- 用户侧最终产物必须是TravelGuide；ItineraryPlan只是其中的每日行程核心。
- 单目的地表示一个城市或旅行区域，内部必须允许多个游玩地点，不得把目的地等同于单个景点。

## 技术约束

- 前端使用Vue 3 + Vite + Element Plus。
- 后端使用Python + FastAPI + Pydantic。
- 业务编排使用LangGraph。
- 结构化数据使用MySQL，RAG向量数据使用Chroma。
- 外部工具通过旅游MCP Server统一暴露。
- 模型通过统一LLMProvider调用，不得在业务服务中写死模型平台、Base URL或模型名。
- API Key只从后端环境变量读取，不得进入前端、代码、文档、日志或测试fixture。
- LangGraph节点应尽量是可单独测试的普通函数。
- 共享Schema集中放置，不得在三个模块中重复定义。

## 协作约束

- 不得自行修改 `CONTRACTS.md` 定义的字段或枚举。
- 若现有契约无法完成任务，先提出最小变更建议和受影响模块，等待三人确认。
- 不重写其他成员负责的模块；需要模拟依赖时使用符合契约的fake/stub。
- 每个功能至少包含正常场景、失败场景和数据不足场景。
- AI生成代码必须解释关键业务判断，避免只有框架代码没有可验证逻辑。

## 建议代码边界

```text
frontend/                     Vue应用
backend/app/api/              FastAPI路由
backend/app/schemas/          共享Pydantic对象
backend/app/graph/            LangGraph状态与节点
backend/app/services/         需求、推荐、规划、验证和重规划服务
backend/app/providers/        MySQL、Chroma、地图、天气和模拟Provider
backend/app/mcp_server/       MCP工具实现
backend/tests/                单元和集成测试
data/                         小规模试点数据和导入脚本
```

## 完成任务时

AI必须报告：

- 修改了哪些文件。
- 实现了哪个业务流程。
- 使用了哪些契约。
- 运行了哪些测试。
- 哪些数据或依赖仍是模拟实现。
- 是否影响其他成员的接口。
