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
