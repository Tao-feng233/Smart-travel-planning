# AI旅行决策与动态行程助手：项目启动包 v0.3

这套文件是项目的统一事实来源，供三位成员及各自的AI助手共同使用。目标不是一次写完所有产品文档，而是先固定范围、术语、接口和分工，使三条开发线能够并行并最终集成。

## 当前项目定义

系统通过自然语言收集用户需求，只从当前知识库和事实库中数据覆盖达到规划门槛的目的地中进行推荐；P0完整支持一个旅行目的地内的多个游玩地点，并预留多目的地扩展结构，完成候选筛选、联合规划、攻略组装、约束验证、修改和局部重规划。

第一版强调“覆盖范围有限、业务闭环完整”。它不是全国旅游平台，不负责真实支付、出票或酒店预订。

## 使用前先填写

正式编码前，由三人共同确认：

```text
知识库数据范围与版本：待填写
规划就绪目的地生成方式：由KnowledgeCoverage自动判断
主LLM Provider及模型：待验证
备用LLM Provider及模型：P1待验证
地图数据方式：真实API / 模拟Provider
天气数据方式：真实API / 模拟Provider
代码仓库地址：待定
```

## 文件阅读顺序

### 三位项目成员

1. `PROJECT_OVERVIEW.md`：从业务到技术的项目全局说明，第一次了解项目先读这一份。
2. `TRAVEL_GUIDE_SPEC.md`：最终攻略七部分的内容、字段、数据收集要求和P0/P1范围。
3. `DATA_REQUIREMENTS_CATALOG.md`：所有需要收集的数据类别和具体字段。
4. `DATA_SOURCE_ASSESSMENT_TEMPLATE.md`：数据尚未确定时用于逐项验证和记录降级方案。
5. `DATA_RESEARCH_TASK_BRIEF.md`：可直接交给独立数据调研任务的说明。
6. `MODEL_PROVIDER_AND_SECRETS.md`：模型抽象、主备Provider和API Key配置。
7. `TEAM_PROJECT_PLAN.md`：三人实际执行的任务、依赖、联调和演示计划。
8. `CONTRACTS.md`：需要开发或联调时查看具体数据和接口格式。

### AI助手

1. `AGENTS.md`：所有AI助手必须遵守的协作和编码规则。
2. `CONTEXT.md`：项目统一术语，避免三个人使用不同概念。
3. `PROJECT_OVERVIEW.md`：项目全局背景和设计。
4. `TRAVEL_GUIDE_SPEC.md`：最终产物的内容和数据要求。
5. `DATA_REQUIREMENTS_CATALOG.md`：数据字段全集。
6. `MODEL_PROVIDER_AND_SECRETS.md`：模型调用与密钥规则。
7. `PROJECT_DESIGN.md`：产品范围、业务流程、技术架构和三人分工。
8. `CONTRACTS.md`：模块之间唯一允许使用的数据和接口格式。
9. `AI_TASK_PROMPTS.md`：三位成员分别交给AI助手的启动提示词。
10. `docs/adr/`：关键架构决定及其理由。

## 三人使用AI的统一方法

每位成员开启新的AI对话时：

1. 把本目录放入代码仓库根目录。
2. 要求AI依次阅读上述文件。
3. 使用 `AI_TASK_PROMPTS.md` 中对应角色的提示词。
4. 要求AI先复述自己的边界、输入、输出和依赖，再开始写代码。
5. AI不得自行修改 `CONTRACTS.md`；确需修改时，必须由三人确认后先更新文档，再改代码。

## 开始编码的最低条件

- 已导入至少一组能通过KnowledgeCoverage检查的试点数据。
- 三人认可 `CONTEXT.md` 中的术语。
- `TripProfile`、`ResourceCandidate`、`ItineraryPlan`、`Conflict` 和 `PlanState` 的JSON格式不再随意变化。
- 每条开发线都能使用模拟数据独立运行。
- 已建立覆盖主要业务分支的回归测试场景，不要求提前固定最终演示文案。

## 推荐的三条演示场景

1. 用户不知道去哪：系统追问、RAG检索、LLM比较目的地并生成完整攻略。
2. 用户已确定一个目的地：系统生成包含抵达、准备、住宿、多个游玩地点、餐饮和交通的完整攻略。
3. 用户起晚或遇到下雨：系统锁定已完成/已预约节点，只重规划剩余部分。

双目的地真实规划为P1演示，有余力时再加入。
