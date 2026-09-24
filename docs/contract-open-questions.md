# 契约待确认项（由 C 线在实现共享 Schema 时登记）

登记人：成员 C　登记日期：2026-09-24

实现 `backend/app/schemas/` 时，`CONTRACTS.md` 中有一些字段**只给了示例值、
没有给出完整取值集合或嵌套结构**。按 `AGENTS.md`“不得自行修改契约枚举”的要求，
这些字段先用宽松类型（`str` 或最小结构）接住，不推断完整枚举。
下表需要在三人共同确认后收紧，并**先改 `CONTRACTS.md` 再改代码**。

## 1. 只给示例值、未定义取值集合的字段（当前用 `str`）

| 对象 | 字段 | 契约示例值 | 影响 |
|---|---|---|---|
| TripProfile | `pace` | `RELAXED` | B 提取节奏、C 校验强度时无法做枚举校验 |
| TripProfile | `interests[]` / `avoidances[]` | `FOOD`、`HIGH_INTENSITY_HIKING` | 过滤与匹配只能做字符串比较 |
| TripProfile | `fixed_facts[]` / `hard_constraints[]` / `soft_preferences[]` | `[]`、中文短句 | 元素结构未定义，暂用 `list[str]` |
| DestinationRequest | `priority` | `HIGH` | 排序逻辑依赖文字 |
| ResourceCandidate | `physical_intensity` / `weather_sensitivity` | `LOW` | C3 前置过滤需要明确等级 |
| DayPlan | `intensity_level` | `LOW` | 用户"减轻强度"修改无法量化 |
| TravelLeg | `walking_burden` | `LOW` | 同上 |
| Conflict | `type` / `scope` | `TIME_WINDOW` / `DAY` | C5 验证器需要固定类型才能写规则 |
| RepairOption | `action` | `REORDER_NODES` | C6 自动修复需要可枚举动作集 |
| PlanState | `stage` | `VALIDATING` | LangGraph 节点跳转条件需要固定阶段名 |

**建议**：尽快补一份取值集合（例如 `pace = RELAXED | MODERATE | INTENSE`），
因为这 8 处直接决定 C3/C4/C5/C6 能否写出确定性规则。

## 2. 文档未规定的嵌套结构（当前做了最小推断）

| 位置 | 契约原文 | 本实现推断 | 说明 |
|---|---|---|---|
| MCP `search_planning_ready_destinations` 输入 | 字段名 `travel_dates` | `DateRange{start_date, end_date}` | 也可为日期数组，需确认 |
| MCP `get_weather` 输出 | 字段名 `temperature_range` | `TemperatureRange{min_celsius, max_celsius}` | 单位固定为摄氏度 |
| MCP `search_travel_knowledge` 输出 | “输出：`Evidence[]`” | `{ "evidence": [...] }` | 顶层是否包装未规定 |
| MCP `get_place_facts` 输出 | “输出：结构化事实及有效期” | `{ "facts": [...] }` | 同上 |
| TravelGuide 住宿候选 | `price_range` | `PriceRange{min_amount, max_amount, currency, status}` | `status` 用于标 KNOWN/ESTIMATED/UNKNOWN |
| TravelGuide 预算 | “所有金额必须标识 KNOWN/ESTIMATED/UNKNOWN” | 平铺金额字段 + `cost_items[]` | 用 `CostItem` 承载状态标识 |
| Evidence `entity_type` | 示例值 `VISIT_PLACE` | `ResourceType` 全集 + `DESTINATION` / `ACTIVITY_AREA` / `INTERCITY_OPTION` | 证据需要能指向目的地本身 |
| KnowledgeCoverage `destination_profile_status` | 示例值 `AVAILABLE` | 复用 `AcquisitionStatus` | 两处取值集合一致 |
| PlanState 的 `profile` / `current_plan` / `current_guide` | 示例写作 `{}` | 用 `null` 表示“尚未产生” | `{}` 无法通过校验 |

## 3. 两份文档之间的不一致

| 冲突点 | `CONTRACTS.md` | `AI_TASK_PROMPTS.md` |
|---|---|---|
| MCP 工具数量 | §12 列出 6 个工具 | 成员 A 提示词写“三个MCP工具” |

**建议**：以 `CONTRACTS.md` 为准，P0 至少实现 3 个可独立调用的工具，
其中 `search_planning_ready_destinations`、`search_travel_knowledge`、
`get_place_availability` 为必须项（分别支撑推荐、RAG 证据和前置过滤）。

---

## 4. 实现 LangGraph 阶段发现的语义问题（2026-09-24 补充）

第 2 步（FastAPI + LangGraph）实现时暴露出 5 个契约层面解释不清的地方。
C 线已按"最小改动 + 不破坏其他线"的方式落地，全部需要三人确认。

### 4.1 `TripProfile` 必须允许"还没问全"的状态（重要）

**问题**：`CONTRACTS.md` §1 的示例 JSON 里所有字段都是必填。
但 `CONTEXT.md` 明确 `TripProfile`“会随着对话持续更新”，
而且该对象自带 `missing_fields` 字段——如果画像必须填满所有字段才能存在，
`missing_fields` 就永远是空的，追问也就无从进行。

**C 线的处理**：除 `session_id` 外，可缺失的字段一律允许为 `None`
（`departure_city`、`start_date`、`end_date`、`traveler_count`、
`traveler_composition`、`budget`）。

**影响**：B 线的 `TripProfile` 提取（B2）直接受益——LLM 可以只填已识别的字段。

**需确认**：这个解释是否写回 `CONTRACTS.md`（把 §1 的示例说明为"信息齐全的终态"）。

### 4.2 `PlanState` 没有承载"本轮用户输入"的位置

**问题**：LangGraph 的入口节点需要读用户这一轮说的话，但 `PlanState` §11 没有该字段；
契约又规定不得自行增删字段。

**C 线的处理**：用 LangGraph 1.x 的 `context_schema`（运行期上下文）传递，
自定义 `TurnContext` 放在 `backend/app/graph/context.py`，不进入契约状态。

**副作用**：中间检索结果（`PlanningReadyDestination[]`）也只能放在上下文里，
因此**前端拿不到"原始候选"，只能看到已经生成的 `DestinationRecommendation`**。
如果 B 线需要展示原始候选，需要给契约加字段或在 REST 层另开字段。

### 4.3 `PlanState.stage` 的取值集合

**问题**：契约只给了示例值 `VALIDATING`。

**C 线的处理**：在 `backend/app/graph/stages.py` 定义 11 个阶段名：

```text
CREATED / PARSING_REQUEST / CHECKING_FIELDS / ASKING_CLARIFICATION /
RETRIEVING_DESTINATIONS / RECOMMENDING_DESTINATIONS /
AWAITING_DESTINATION_CONFIRMATION / INSUFFICIENT_DATA /
PLANNING / VALIDATING / REPAIRING / READY
```

**需确认**：B 线前端会按 stage 分支渲染，确认后应写回契约。

### 4.4 `Budget` 无法表达"预算不限"

**问题**：`Budget.amount` 是必填数字。用户回答"预算无所谓"时无法表示，
会导致重复追问。

**建议**：确认一种表达方式，例如 `amount` 允许为 `null` 且
`flexibility=NEGOTIABLE` 表示"无明确上限"。

### 4.5 REST 响应体未在契约中定义

**问题**：`CONTRACTS.md` §14 只列出接口路径，没有响应体结构。
C 线在 `backend/app/schemas/api.py` 定义了 `AssistantReply`（含
`kind / text / questions / missing_fields / suggestions / notes`）等传输对象。

**说明**：这些是接口层对象，不是领域契约；但它们决定 B 线前端的对接方式，
确认后建议一并写进契约。

---

## 5. v0.4 对本清单的处理结果（2026-09-24 更新）

启动包 v0.4 上线后，本清单前面的问题大部分被正式契约解决了。
下面逐条对账，避免三个人重复讨论已经定论的事。

### 5.1 已被 v0.4 解决

| 原问题 | v0.4 的处理 | 位置 |
|---|---|---|
| 第 1 节：9 个字段只有示例值、没有取值集合 | 全部枚举已定义，含 `pace = RELAXED / BALANCED / INTENSE`、`ConflictSeverity`、`NodeType`、`TravelMode` 等 | `CONTRACTS.md` §1.3、§8 |
| 第 2 节：`travel_dates`、`temperature_range` 嵌套结构未定义 | 由 v0.4 的 MCP 工具契约与 `Money`/`TimeWindow` 统一类型取代 | §1.1、§1.2、§12 |
| 第 3 节：MCP 工具 3 个还是 6 个 | 定为 **9 个**，并重新命名 | §12.1–§12.9 |
| 4.1 `TripProfile` 允许不完整 | ⚠️ **未解决**，见 5.2 | — |
| 4.2 `PlanState` 没有承载本轮用户输入的位置 | 明确为 REST 请求参数（`{text, expected_profile_version?}`），不进状态 | §13.1 |
| 4.3 `PlanState.stage` 取值集合 | 定义完整状态链 `PARSING → ASKING_CLARIFICATION → RECOMMENDING → WAITING_CONFIRMATION → PLANNING → VALIDATING → COMPOSING_GUIDE → PRESENTED → REPLANNING` | §14 |
| 4.4 `Budget` 无法表达"预算不限" | `Money` 支持 `amount / min_amount / max_amount` 可空组合 + `budget_flexibility` | §1.1、§2.3 |
| 4.5 REST 响应体未定义 | 统一信封 `{ok, data, warnings, error, trace_id}` + 8 个错误码 | §13 |
| `RepairOption.action`、`Conflict.type` 取值集合 | 已完整定义 | §8.1、§8.2 |
| `PlanNode` 的 `TRANSFER` 歧义 | `NodeType` 删除 `TRANSFER`，普通交通只用 `TravelLeg` | §1.3 |

### 5.2 仍然存在的问题（需要三人拍板）

**Q1（阻塞 C1）：`TripProfile` 在 v0.4 里仍是全字段必填，无法表示"还没问全"的画像。**

`CONTRACTS.md` §2.3 的 `TripProfile` 带 `missing_fields` 字段，说明设计上本来就预期
画像可以处于"部分已知"状态；但 §2.3 的示例与 `contracts/contract_models.py` 的
基线实现都是全字段必填（`departure_city`、`start_date`、`budget`、`pace` 等都没有默认值）。

后果：**"缺日期/预算就追问"这条 P0 要求无法用一个合法的 `TripProfile` 对象表达**——
在补齐所有字段之前，根本构造不出这个对象。

C1 会先按"可缺失字段允许为 `None` + 用 `missing_fields` 记录"实现，
但必须三人确认后写回 `CONTRACTS.md`。

**Q2：统一 Error / Warning 对象的结构未定义。**

§13 规定了信封里有 `warnings` 和 `error` 两个字段，但没有定义它们的内部结构。
C1 需要一个最小结构（例如 `code / message / details`），
并且要与 §13.3 的 8 个错误码、`DATA_PROVIDER_ARCHITECTURE.md` 的
`DATA_MISSING` / `NO_FEASIBLE_PLAN` 对齐。

**Q3：9 个 MCP 工具的 Request / Response 结构只有字段描述。**

§12 给出了每个工具的作用与输入输出要点，但基线 `contract_models.py` 只实现了
10 个模型，没有实现任何 MCP Request/Response。
C1 会按 §12 的描述补齐，遇到的每个歧义点都会登记在这里。
