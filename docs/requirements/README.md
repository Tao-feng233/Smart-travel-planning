# 原始需求文档（项目输入）

本目录保存项目**最初的原始需求材料**，属于"输入"，不是"设计"。
设计结论以仓库根目录的 `PROJECT_DESIGN.md`、`TRAVEL_GUIDE_SPEC.md`、
`CONTRACTS.md` 为准；两者冲突时以后者为准。

保留原件的意义：三个人（以及各自的 AI 助手）判断"某个功能到底为什么存在"时，
可以回到最初的需求原话，而不是只看到已经被裁剪过的设计文档。

## 文件清单

| 文件 | 作者/来源 | 内容 |
|---|---|---|
| `需求汇总-初版.md` | 团队 | 住宿、美食、景点、出行四类需求，以及"需求分析"结论 |
| `旅游规划需求痛点-刘.md` | 刘 | 六条口语化需求，偏用户视角 |
| `旅游痛点-行业建议-01.jpg` | 行业资料 | 痛点与行业建议配图（内容未结构化） |

---

## 原始需求 → 项目设计的对应关系

这张表用来回答"我们有没有漏掉用户当初提的东西"。

### 住宿

| 原始说法 | 项目中的位置 | P0 / P1 |
|---|---|---|
| 酒店、旅馆信息获取，通过 API 还是其他方法 | A 线数据源调研（`DATA_SOURCE_ASSESSMENT_TEMPLATE.md`） | P0 评估 |
| 推荐预定 | `TravelGuide` 第四部分：住宿候选，不声称"可订" | P0 候选；**P1 实时库存与预订** |
| 考虑出行距离，如何让 AI 综合规划路线 | `StaySegment` + `TravelLeg` + `commute_summary` | P0 |

### 美食

| 原始说法 | 项目中的位置 | P0 / P1 |
|---|---|---|
| 周边饮食、本地特色、具体美食地点 | `RestaurantCandidate`，插入每日行程用餐节点 | P0（数据不足时降级为"用餐区域+类型"） |
| 如何判断评价情况（是否用评论做向量库） | 证据类型 `REVIEW_SUMMARY`，`source_type=GUIDE/PLATFORM` | P0 可留空；**P1 评论聚合** |
| 若在向量库中放攻略，要避免 AI 读到攻略内容影响判断 | **ADR 0004：LLM 不是旅游事实来源**；认知知识与结构化事实分离（ADR 0001）；`Evidence` 必须带 `source_type` 与 `verification_status` | 已作为硬约束落地 |

> 这条需求当年点出的风险，现在由"事实走 MCP / 认知走 RAG / LLM 只能选候选里的 ID"三件事共同解决。

### 景点

| 原始说法 | 项目中的位置 | P0 / P1 |
|---|---|---|
| 基础信息、开放时间 | `ResourceCandidate.availability` + 前置过滤 | P0 |
| 天气情况（可能用 API） | `get_weather` MCP 工具 + 行前准备规则 | P0（可模拟 Provider） |
| 人流情况、分时段、智能推荐时间路线 | `crowd_pattern` 只输出 LOW/MEDIUM/HIGH/EXTREME | **P1** |
| 提取关键内容作为向量数据库、辅助 AI 建立景点认知 | Chroma 认知卡片 + `search_travel_knowledge` | P0（A2/A3） |
| 提供景色图片 | 未纳入 P0 | P2 |

### 出行

| 原始说法 | 项目中的位置 | P0 / P1 |
|---|---|---|
| 订票、获取列车/航班时刻表 | `IntercityOption` 只给方式、时间窗、价格区间 | P0；**具体班次与订票为 P1**，且不得虚构车次 |
| 票量情况、抢票难度 | 未纳入 | P2 |
| 出站到酒店的路线、酒店到景点的规划 | `ArrivalPlan` + 每日 `TravelLeg` | P0 |
| 考虑体力消耗来规划出行时机 | `physical_intensity` + `intensity_level` + 用户 `mobility_constraints` | P0 |
| 打车、特色旅游大巴等 | `recommended_mode: WALK/METRO/BUS/TAXI/OTHER` | P0 |

### 需求分析

| 原始说法 | 项目中的位置 | 状态 |
|---|---|---|
| **不能直接给路线**，要通过构建需求列表一步步询问用户 | LangGraph 追问回路 `check_missing_fields → ask_clarification` | ✅ 已在步骤 2 实现（`backend/app/services/missing_fields.py`） |
| 根据用户实际需求选择旅游地点 | 硬条件初筛 → RAG 证据 → LLM 比较（ADR 0002） | P0 |
| 识别购物需求、喜欢的景色、旅游节奏 | `TripProfile.interests / avoidances / pace` | P0（B2） |

---

## 三条"原始需求没有被照单全收"的地方

如果三人对下面这些有不同意见，应该先讨论、再改 `PROJECT_DESIGN.md`：

1. **真实订票、余票、抢票**：初版需求提到"智能规划购票"，项目明确划入 P1/P2，
   第一版只给方式与价格区间。原因是需要商业授权且不稳定。
2. **评论数据进向量库**：需求提出过这个想法，项目把它限制为"证据的一种，
   必须带来源与核验状态"，且不属于 P0。
3. **全国范围**：明确不做，只在数据覆盖达标的目的地中推荐。
