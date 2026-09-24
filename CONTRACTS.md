# 共享数据与接口契约 v0.4

> 本文件是字段、类型、枚举、接口和业务不变量的唯一裁决源。`TRAVEL_GUIDE_SPEC.md`只定义用户看到的内容，`DATA_REQUIREMENTS_CATALOG.md`只定义需要采集的数据。若其他文件与本文件冲突，以本文件为准并同步修正文档。

## 0. 版本与时间规则

- 启动包版本、契约版本和其他文档版本相互独立；每份文件必须在标题声明自身版本。
- 兼容当前启动包：`starter_pack_version = 0.4`。
- 日期使用 `YYYY-MM-DD`。
- 时间点使用带UTC偏移的RFC 3339，例如 `2026-10-03T09:00:00+08:00`。
- `TripProfile.start_date`与`end_date`均计入旅行天数，`duration_days = end_date - start_date + 1`。
- `StaySegment.check_in_date`为入住日（含），`check_out_date`为退房日（不含）。
- 每份攻略保存IANA时区，例如 `Asia/Shanghai`。

## 1. 通用类型与枚举

### 1.1 Money

```json
{
  "amount": null,
  "min_amount": 50.0,
  "max_amount": 80.0,
  "currency": "CNY"
}
```

不变量：固定金额使用`amount`；区间使用`min_amount/max_amount`；两种形式不得同时出现。

### 1.2 TimeWindow

```json
{
  "start_at": "2026-10-03T09:00:00+08:00",
  "end_at": "2026-10-03T17:00:00+08:00"
}
```

### 1.3 核心枚举

```text
RunMode                 DEMO | VERIFIED
PlanValidationStatus    PENDING | VALID | INVALID
DataAssuranceStatus     VERIFIED | DEGRADED | MOCK | INSUFFICIENT
GuideLifecycleStatus    DRAFT | CONFIRMED | EXECUTING | COMPLETED | OUTDATED
GuideReadiness           READY | READY_WITH_WARNINGS | NOT_READY
AvailabilityStatus      AVAILABLE | CONDITIONAL | UNAVAILABLE | UNKNOWN
AcquisitionStatus       UNASSESSED | AVAILABLE | LIMITED | UNAVAILABLE | MOCK_ONLY
VerificationStatus      PENDING | VERIFIED | REVIEW | REJECTED
SourceType              OFFICIAL | AUTHORITY | PLATFORM | GUIDE | MANUAL | DERIVED | MOCK
ResourceType            VISIT_PLACE | RESTAURANT | LODGING | LODGING_AREA | INTERCITY_OPTION
NodeType                ARRIVAL | CHECK_IN | ATTRACTION | MEAL | REST | WALK_AREA | SHOPPING | LODGING | FREE_TIME
TravelMode              WALK | METRO | BUS | TAXI | BIKE | RAIL | FLIGHT | INTERCITY_BUS | OTHER
PricingScope            PER_PERSON | PER_GROUP | PER_ROOM | PER_NIGHT | PER_ITEM
CostStatus              KNOWN | ESTIMATED | UNKNOWN
ConstraintKind          FIXED | NEGOTIABLE_HARD | SOFT
ConflictSeverity        WARNING | ERROR
```

普通节点之间的交通只能使用`TravelLeg`，不得创建`TRANSFER`类型的`PlanNode`。

## 2. 用户需求与约束

### 2.1 Constraint

```json
{
  "constraint_id": "constraint_001",
  "kind": "NEGOTIABLE_HARD",
  "field": "budget.total",
  "operator": "LTE",
  "value": 5000,
  "priority": 100,
  "source_text": "预算最多五千"
}
```

`operator`：`EQ | NE | LT | LTE | GT | GTE | IN | NOT_IN | CONTAINS`。

### 2.2 DestinationRequest

```json
{
  "destination_id": "dest_001",
  "name": "示例目的地",
  "desired_days": 4,
  "min_days": 3,
  "max_days": 5,
  "priority": "HIGH",
  "fixed": false,
  "user_reason": "想多体验当地文化"
}
```

### 2.3 TripProfile

```json
{
  "session_id": "sess_001",
  "profile_version": 1,
  "departure_city": "上海",
  "start_date": "2026-10-02",
  "end_date": "2026-10-05",
  "duration_days": 4,
  "timezone": "Asia/Shanghai",
  "traveler_count": 2,
  "traveler_composition": {"adults": 2, "children": 0, "seniors": 0},
  "budget": {"amount": 5000, "min_amount": null, "max_amount": null, "currency": "CNY"},
  "budget_flexibility": "NEGOTIABLE",
  "pace": "RELAXED",
  "interests": ["FOOD", "CULTURE"],
  "must_visit_resource_ids": [],
  "avoidances": ["HIGH_INTENSITY_HIKING"],
  "mobility_constraints": [],
  "dietary_constraints": [],
  "lodging_preferences": ["QUIET", "NEAR_TRANSIT"],
  "transport_preferences": ["METRO", "TAXI"],
  "earliest_day_start": "08:30",
  "latest_day_end": "21:00",
  "destination_mode": "UNKNOWN",
  "destination_requests": [],
  "constraints": []
}
```

`duration_days`必须与日期区间一致。`fixed_facts/hard_constraints/soft_preferences`不再使用无结构数组，统一转换为`Constraint[]`和明确字段。

`TripProfile`是**信息完整**的画像：`departure_city`、`start_date`、`end_date`、
`duration_days`、`traveler_count`、`traveler_composition`、`budget`、
`budget_flexibility`、`pace`、`destination_mode`均为必填。
对话过程中尚未补齐的画像使用下面的`TripProfileDraft`表示。

### 2.4 TripProfileDraft

用于“缺日期/预算就追问”这条 P0 流程：除`session_id`外所有字段允许为空，
`missing_fields`只属于 Draft。

```json
{
  "session_id": "sess_001",
  "profile_version": 0,
  "departure_city": "上海",
  "start_date": null,
  "end_date": null,
  "duration_days": null,
  "timezone": "Asia/Shanghai",
  "traveler_count": 2,
  "traveler_composition": null,
  "budget": null,
  "budget_flexibility": null,
  "pace": null,
  "interests": ["FOOD"],
  "must_visit_resource_ids": [],
  "avoidances": [],
  "mobility_constraints": [],
  "dietary_constraints": [],
  "lodging_preferences": [],
  "transport_preferences": [],
  "earliest_day_start": null,
  "latest_day_end": null,
  "destination_mode": "UNKNOWN",
  "destination_requests": [],
  "constraints": [],
  "missing_fields": ["start_date", "end_date", "budget"]
}
```

规则：

- 字段集合与`TripProfile`一致，但除`session_id`外均可为空。
- 已填字段仍必须自洽：例如同时给出`start_date`和`end_date`时，结束日期不得早于开始日期。
- `missing_fields`记录**仍需用户补充的关键字段**，由系统计算，不由 LLM 随意填写。

### 2.5 finalize_trip_profile

Draft 补齐后转换为正式`TripProfile`：

```text
finalize_trip_profile(draft: TripProfileDraft) -> TripProfile
```

**必须由用户提供、不得由系统替他假设的字段**：

```text
departure_city, start_date, end_date, traveler_count, budget
```

缺任一字段时抛出`IncompleteProfileError(missing_fields)`，**不得**生成正式`TripProfile`。

**可以推导或取默认值的字段**：

```text
duration_days          由 start_date/end_date 推导（含首尾两天）
traveler_composition   未说明构成时按成人计（adults = traveler_count）
budget_flexibility     未说明时取 NEGOTIABLE
pace                   未说明时取 BALANCED
destination_mode       未说明时取 UNKNOWN
```

转换结果必须通过`TripProfile`的全部校验：`duration_days`与日期区间一致、
`traveler_composition`合计等于`traveler_count`。

## 3. 数据覆盖与本次规划就绪

### 3.1 DestinationCoverageSnapshot

描述长期数据覆盖，不直接等同于本次可规划。

```json
{
  "coverage_snapshot_id": "cov_001",
  "destination_id": "dest_001",
  "coverage_version": "2026-09-24-v1",
  "category_status": {
    "destination_profile": "AVAILABLE",
    "visit_places": "AVAILABLE",
    "opening_rules": "AVAILABLE",
    "routes": "AVAILABLE",
    "lodging": "LIMITED",
    "restaurants": "LIMITED",
    "intercity_transport": "LIMITED",
    "preparation_rules": "AVAILABLE",
    "weather": "MOCK_ONLY"
  },
  "missing_capabilities": ["REALTIME_HOTEL_AVAILABILITY"],
  "evaluated_at": "2026-09-24T10:00:00+08:00"
}
```

### 3.2 PlanningReadinessEvaluation

针对当前`TripProfile`动态判断。

```json
{
  "readiness_id": "ready_001",
  "destination_id": "dest_001",
  "trip_profile_version": 1,
  "evaluated_for": {
    "start_date": "2026-10-02",
    "end_date": "2026-10-05",
    "duration_days": 4,
    "traveler_count": 2
  },
  "required_capabilities": ["VISIT_PLACES", "OPENING_RULES", "ROUTES", "LODGING"],
  "failed_requirements": [],
  "coverage_snapshot_id": "cov_001",
  "ruleset_version": "readiness-1.0",
  "planning_ready": true,
  "evaluated_at": "2026-09-24T10:05:00+08:00"
}
```

LLM只能推荐`planning_ready=true`的候选ID。

## 4. 来源、事实、证据与数据快照

### 4.1 FactRecord

MySQL中的结构化事实原始记录。

```json
{
  "fact_record_id": "fact_001",
  "entity_id": "poi_001",
  "fact_type": "OPENING_HOURS",
  "value": {"open": "09:00", "last_entry": "16:30", "close": "17:00"},
  "source_type": "OFFICIAL",
  "source_ref": "https://example.com/source",
  "collected_at": "2026-09-24T09:00:00+08:00",
  "valid_until": "2026-10-10T23:59:59+08:00",
  "acquisition_status": "AVAILABLE",
  "verification_status": "VERIFIED",
  "raw_snapshot_ref": "raw/poi_001_20260924.json",
  "notes": null
}
```

### 4.2 Evidence

Chroma中的RAG认知证据，不直接参与确定性计算。

```json
{
  "evidence_id": "ev_001",
  "entity_id": "poi_001",
  "entity_type": "VISIT_PLACE",
  "content": "该区域适合慢节奏文化游览，雨天仍可安排室内活动。",
  "source_type": "GUIDE",
  "source_ref": "https://example.com/guide",
  "collected_at": "2026-09-24T09:00:00+08:00",
  "valid_until": null,
  "acquisition_status": "AVAILABLE",
  "verification_status": "REVIEW",
  "tags": ["CULTURE", "RELAXED", "INDOOR"]
}
```

### 4.3 PlanningFact

从有效`FactRecord`归一化后进入本次计算的事实。

```json
{
  "planning_fact_id": "pf_001",
  "fact_record_id": "fact_001",
  "entity_id": "poi_001",
  "fact_type": "OPENING_HOURS",
  "normalized_value": {"open": "09:00", "last_entry": "16:30", "close": "17:00"},
  "applies_from": "2026-10-02",
  "applies_to": "2026-10-05",
  "assurance": "VERIFIED"
}
```

### 4.4 DataSnapshot

```json
{
  "data_snapshot_id": "snap_001",
  "created_at": "2026-09-24T10:10:00+08:00",
  "run_mode": "DEMO",
  "trip_profile_version": 1,
  "readiness_evaluation_ids": ["ready_001"],
  "planning_fact_ids": ["pf_001"],
  "evidence_ids": ["ev_001"],
  "provider_versions": ["mock-provider-1.0"],
  "ruleset_versions": ["readiness-1.0", "validation-1.0"],
  "expired_items": [],
  "degraded_items": [],
  "mock_items": ["weather:dest_001"],
  "unknown_items": []
}
```

关系：`FactRecord → PlanningFact → ItineraryPlan`；`Evidence → LLM解释与推荐`；二者共同进入`DataSnapshot`和攻略来源部分。

## 5. 资源候选

### 5.1 ResourceCandidateBase

```json
{
  "resource_id": "poi_001",
  "resource_type": "VISIT_PLACE",
  "destination_id": "dest_001",
  "area_id": "area_001",
  "name": "示例博物馆",
  "address": "示例地址",
  "latitude": 30.0,
  "longitude": 104.0,
  "categories": ["CULTURE", "INDOOR"],
  "suggested_duration_minutes": 120,
  "availability_status": "AVAILABLE",
  "planning_fact_ids": ["pf_001"],
  "evidence_ids": ["ev_001"]
}
```

具体资源Schema：

- `VisitPlaceCandidate`：增加开放窗口、预约、体力、室内外、天气敏感度、票价。
- `LodgingCandidate`：增加住宿类型、价格区间、评分、质量标签、设施、入住退房时间、交通适配、库存可信度。
- `RestaurantCandidate`：增加菜系、人均、营业时间、饮食标签、辣度、预约和路线适配。
- `IntercityOption`：增加起终站、方式、门到门耗时、价格区间、预订和行李提示。
- `PreparationRule`：增加触发条件、准备物品、优先级、完成期限和原因。

字段全集以本文件附录A为准。

### 5.2 判别联合类型成员（Q4 定案，2026-09-24）

```text
ResourceCandidateUnion = VisitPlaceCandidate | LodgingCandidate
                       | RestaurantCandidate | LodgingAreaCandidate
```

规则：

1. 上述成员**全部继承`ResourceCandidateBase`**，统一使用
   `resource_id`、`destination_id`、`resource_type`三个字段；
2. `LodgingCandidate`**不再使用`lodging_id`作为共享主键**；
   外部数据里的`hotel_id`、`lodging_id`等由 A 线在 Provider 层归一化为`resource_id`；
3. `LodgingAreaCandidate`为可选成员，字段以本文件附录A为准；
4. `IntercityOption`与`PreparationRule`**不属于**`ResourceCandidateUnion`，
   分别保留各自主键`option_id`与`rule_id`；
5. 判别字段统一为`resource_type`，取值见 §1.3。

## 6. 目的地推荐

```json
{
  "destination_id": "dest_001",
  "readiness_id": "ready_001",
  "suggested_days": 4,
  "suitable": true,
  "reason": "文化和美食资源与用户偏好匹配，通勤压力可控。",
  "tradeoffs": ["自然景观比例较低"],
  "risk_flags": ["HOLIDAY_CROWD"],
  "evidence_ids": ["ev_001"]
}
```

推荐对象必须来自`search_planning_ready_destinations`返回集合。

## 7. 行程规划与费用

### 7.1 TripSegment

```json
{
  "segment_id": "seg_001",
  "destination_id": "dest_001",
  "start_date": "2026-10-02",
  "end_date": "2026-10-05",
  "allocated_days": 4
}
```

### 7.2 StaySegment

```json
{
  "stay_segment_id": "stay_001",
  "check_in_date": "2026-10-02",
  "check_out_date": "2026-10-06",
  "lodging_id": "hotel_001",
  "lodging_area": "示例区域",
  "is_user_booked": false,
  "locked": false,
  "switch_reason": null
}
```

### 7.3 PlanNode（内部精简对象）

```json
{
  "node_id": "node_001",
  "node_type": "ATTRACTION",
  "resource_id": "poi_001",
  "start_at": "2026-10-03T09:00:00+08:00",
  "end_at": "2026-10-03T11:00:00+08:00",
  "cost_item_ids": ["cost_001"],
  "reason": "符合文化偏好且位于当日主要区域",
  "locked": false,
  "completed": false,
  "evidence_ids": ["ev_001"]
}
```

### 7.4 TravelLeg

```json
{
  "leg_id": "leg_001",
  "from_node_id": "node_001",
  "to_node_id": "node_002",
  "recommended_mode": "METRO",
  "alternative_modes": ["TAXI"],
  "depart_at": "2026-10-03T11:00:00+08:00",
  "arrive_at": "2026-10-03T11:25:00+08:00",
  "duration_minutes": 25,
  "distance_km": 6.4,
  "cost_item_ids": ["cost_002"],
  "congestion_note": "高峰时段打车可能拥堵",
  "walking_burden": "LOW",
  "transfer_count": 1,
  "reason": "地铁时间更稳定",
  "source": "MAP_PROVIDER",
  "is_estimated": false
}
```

### 7.5 DayPlan（内部对象）

```json
{
  "date": "2026-10-03",
  "segment_id": "seg_001",
  "stay_segment_id": "stay_001",
  "node_ids": ["node_001", "node_002"],
  "travel_leg_ids": ["leg_001"]
}
```

### 7.6 CostItem

```json
{
  "cost_item_id": "cost_001",
  "category": "TICKET",
  "item_ref": "poi_001",
  "unit_price": {"amount": 50, "min_amount": null, "max_amount": null, "currency": "CNY"},
  "quantity": 2,
  "pricing_scope": "PER_PERSON",
  "status": "KNOWN",
  "paid": false,
  "refundable": null,
  "evidence_ids": ["ev_price_001"]
}
```

### 7.7 BudgetSummary

由`CostItem[]`唯一计算，不允许各模块直接维护另一套总额。

```json
{
  "currency": "CNY",
  "total_limit": 5000,
  "known_total": 100,
  "estimated_min_total": 900,
  "estimated_max_total": 1300,
  "remaining_min": 3700,
  "remaining_max": 4100,
  "by_category": {"TICKET": 100, "LOCAL_TRANSPORT": 20},
  "unknown_cost_item_ids": []
}
```

### 7.8 ItineraryPlan

由`TripSegment[]`、`StaySegment[]`、覆盖全部旅行日期的`DayPlan[]`、`PlanNode[]`、`TravelLeg[]`、`CostItem[]`、`BudgetSummary`、计划验证状态和DataSnapshot引用组成。

完整合法JSON位于`fixtures/valid/itinerary_plan.json`，强类型定义位于`contracts/contract_models.py`。文档示例不得使用空对象或引用不存在的节点。

不变量：`days`必须覆盖从`start_date`到`end_date`的每一天；节点不得重叠；相邻地点的时间必须容纳对应`TravelLeg`。

## 8. 验证、修复与备用方案

### 8.1 RepairOption

用于解决当前已检测冲突，是规划器可执行的操作。

```json
{
  "repair_option_id": "repair_001",
  "action": "REORDER_NODES",
  "description": "交换两个活动顺序以满足最晚入园时间",
  "affected_node_ids": ["node_001", "node_002"],
  "requires_user_confirmation": false
}
```

`action`：`REORDER_NODES | MOVE_NODE | REPLACE_RESOURCE | REMOVE_NODE | ADD_REST | CHANGE_TRAVEL_MODE | REQUEST_USER_CHOICE | RELAX_NEGOTIABLE_CONSTRAINT`。

### 8.2 Conflict

```json
{
  "conflict_id": "conflict_001",
  "type": "TIME_WINDOW",
  "severity": "ERROR",
  "scope": "DAY",
  "message": "预计抵达时间晚于最晚入园时间",
  "affected_node_ids": ["node_001", "node_002"],
  "repair_options": [],
  "status": "OPEN"
}
```

`type`：`TIME_WINDOW | OPENING_HOURS | BUDGET_EXCEEDED | DAILY_INTENSITY | DISTANCE_EXCESSIVE | RESERVATION_REQUIRED | WEATHER_UNSUITABLE | DAYS_INSUFFICIENT | CONSTRAINT_VIOLATION | DATA_EXPIRED | DATA_UNKNOWN`。

### 8.3 AlternativePlan

用于攻略中预先说明“如果下雨/起晚/关闭怎么办”，不等同于当前冲突修复动作。

```json
{
  "alternative_plan_id": "alt_001",
  "trigger": "LATE_START",
  "affected_node_ids": ["node_001"],
  "replacement_resource_ids": ["poi_002"],
  "cost_delta": {"amount": 0, "min_amount": null, "max_amount": null, "currency": "CNY"},
  "time_delta_minutes": -60,
  "reason": "减少上午安排并保留已预约项目",
  "requires_user_confirmation": false
}
```

## 9. 用户侧攻略对象

### 9.1 GuideNode（展示对象）

由`PlanNode + ResourceCandidate + PlanningFact`组装，避免规划器复制展示字段。

```json
{
  "node_id": "node_001",
  "node_type": "ATTRACTION",
  "resource_id": "poi_001",
  "name": "示例博物馆",
  "address": "示例地址",
  "start_at": "2026-10-03T09:00:00+08:00",
  "end_at": "2026-10-03T11:00:00+08:00",
  "opening_window": {"start_at": "2026-10-03T09:00:00+08:00", "end_at": "2026-10-03T17:00:00+08:00"},
  "last_entry_at": "2026-10-03T16:30:00+08:00",
  "reservation_required": false,
  "estimated_cost": {"amount": 50, "min_amount": null, "max_amount": null, "currency": "CNY"},
  "reason": "符合文化偏好且位于当日主要区域",
  "tips": ["建议预留安检时间"],
  "locked": false,
  "evidence_ids": ["ev_001"]
}
```

### 9.2 GuideDay

```json
{
  "date": "2026-10-03",
  "day_theme": "城市文化与慢节奏体验",
  "activity_areas": ["示例文化片区"],
  "start_location": "hotel_001",
  "end_location": "hotel_001",
  "nodes": [],
  "travel_legs": [],
  "total_activity_minutes": 360,
  "total_travel_minutes": 50,
  "intensity_level": "LOW",
  "estimated_cost": {"amount": null, "min_amount": 200, "max_amount": 300, "currency": "CNY"},
  "warnings": [],
  "alternative_plan_ids": ["alt_001"]
}
```

### 9.3 TravelGuide

| 字段 | 类型 |
|---|---|
| guide_id/session_id | string |
| guide_version/parent_guide_version | integer/null |
| run_mode | RunMode |
| lifecycle_status | GuideLifecycleStatus |
| plan_validation_status | PlanValidationStatus |
| data_assurance_status | DataAssuranceStatus |
| guide_readiness | GuideReadiness |
| timezone | IANA timezone string |
| trip_summary | TripSummarySection |
| arrival_and_departure | ArrivalAndDepartureSection |
| preparation | PreparationSection |
| lodging | LodgingSection |
| daily_itinerary | GuideDay[] |
| budget_and_alternatives | BudgetAndAlternativesSection |
| sources_and_freshness | SourcesAndFreshnessSection |
| plan_id/plan_version/data_snapshot_id | version references |

各Section的强类型定义位于`contracts/contract_models.py`，完整合法JSON位于`fixtures/valid/travel_guide.json`；两者与本文件共同构成可执行契约，不允许以空对象替代。

发布规则：

- `plan_validation_status=INVALID` → `guide_readiness=NOT_READY`。
- `data_assurance_status=INSUFFICIENT` → `guide_readiness=NOT_READY`。
- `run_mode=DEMO`或`data_assurance_status=MOCK` → 页面必须显示模拟数据标识，不得声称真实可执行。
- 非关键数据降级可进入`READY_WITH_WARNINGS`；关键开放、路线或住宿起点数据缺失时不得发布为READY。

## 10. 状态、版本谱系与重规划

### 10.1 VersionLineage

```json
{
  "change_request_id": "change_001",
  "parent_plan_version": 1,
  "new_plan_version": 2,
  "parent_guide_version": 1,
  "new_guide_version": 2,
  "preserved_node_ids": ["node_001"],
  "changed_node_ids": ["node_002"],
  "removed_node_ids": ["node_003"],
  "replacement_relations": [{"old_node_id": "node_003", "new_node_id": "node_004"}]
}
```

保留节点沿用原ID；替换节点使用新ID；锁定节点变得不可用时产生冲突，不得静默删除。

### 10.2 PlanState

```json
{
  "session_id": "sess_001",
  "stage": "VALIDATING",
  "trip_profile_version": 1,
  "destination_candidate_ids": [],
  "resource_candidate_ids": [],
  "current_plan_id": "plan_001",
  "current_plan_version": 1,
  "current_guide_id": "guide_001",
  "current_guide_version": 1,
  "conflict_ids": [],
  "locked_node_ids": [],
  "completed_node_ids": [],
  "active_incidents": [],
  "data_snapshot_id": "snap_001",
  "repair_attempts": 0,
  "awaiting_user_input": false
}
```

### 10.3 通用重规划流程

```text
interpret_event
→ determine_affected_scope
→ lock_preserved_nodes
→ retrieve_available_resources
→ generate_repair_candidates
→ validate_repair
→ create_new_plan_and_guide_versions
```

起晚、下雨、地点关闭、用户疲劳等只是不同事件输入，不建设互相独立的重规划系统。

## 11. 用户动作

```json
{
  "action_id": "action_001",
  "idempotency_key": "client-generated-uuid",
  "action_type": "MODIFY_GUIDE",
  "session_id": "sess_001",
  "guide_id": "guide_001",
  "expected_guide_version": 1,
  "raw_text": "第二天太累了，下午少安排一个景点",
  "payload": {
    "change_type": "LOWER_INTENSITY",
    "scope_hint": "DAY",
    "date": "2026-10-03",
    "target_node_ids": []
  }
}
```

`action_type`：`SELECT_DESTINATION | CONFIRM_GUIDE | MODIFY_GUIDE | REPORT_INCIDENT`。

`change_type`：`REMOVE_NODE | REPLACE_NODE | ADD_FIXED_NODE | LOWER_INTENSITY | CHANGE_DATE | CHANGE_BUDGET | CHANGE_PACE | CHANGE_LODGING`。

重复`idempotency_key`不得生成重复版本。

## 12. MCP工具契约

契约定义9个工具。P0允许其背后使用Mock、Snapshot、Live或Hybrid Provider，但返回结构必须一致。

### 12.1 `search_planning_ready_destinations`

输入：`TripProfile`。输出：`DestinationRecommendation[] + PlanningReadinessEvaluation[]`。

### 12.2 `search_travel_knowledge`

输入：`query, destination_ids?, entity_types?, top_k?`。输出：`Evidence[]`。

### 12.3 `search_resources`

输入：`resource_type, destination_id, area_ids?, date_range, filters`。输出对应判别联合类型候选。

### 12.4 `get_resource_facts`

输入：`resource_ids[], fact_types?, date_range`。输出：`FactRecord[]`和可用`PlanningFact[]`。

### 12.5 `get_resource_availability`

输入：`resource_id, date, requested_window?`。输出：`AvailabilityStatus, available_windows, reservation_required, reason, planning_fact_ids`。

### 12.6 `get_intercity_options`

输入：`origin_city, destination_id, arrival_or_departure_date, traveler_constraints`。输出：`IntercityOption[]`。

### 12.7 `get_route`

输入：`origin, destination, depart_at?, allowed_modes?`。输出：`RouteOption[]`。

### 12.8 `get_weather`

输入：`destination_id/coordinate, date_range`。输出天气事实及来源状态。

### 12.9 `get_preparation_rules`

输入：`TripProfile, activity_tags[], weather_facts[]`。输出：`PreparationRule[]`。

P0验收：9个工具均有符合契约的可调用实现（允许Mock）；端到端流程必须留下至少目的地搜索、资源搜索、事实查询和路线查询四类调用日志。

## 13. REST接口

统一响应：

```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "error": null,
  "trace_id": "trace_001"
}
```

### 13.1 会话

```text
POST /api/sessions
请求：{run_mode, timezone}
响应：{session_id, PlanState}

POST /api/sessions/{id}/messages
请求：{text, expected_profile_version?}
响应：{stage, assistant_message, trip_profile?, destination_candidates?, guide_id?, conflicts?, degraded_items?}

GET /api/sessions/{id}
响应：PlanState
```

### 13.2 攻略

```text
GET  /api/guides/{id}?version=
响应：TravelGuide

POST /api/guides/{id}/confirm
请求：{expected_guide_version, lock_node_ids[], idempotency_key}
响应：TravelGuide

POST /api/guides/{id}/modify
请求：UserAction(action_type=MODIFY_GUIDE)
响应：{travel_guide, version_lineage, conflicts}

POST /api/guides/{id}/incident
请求：UserAction(action_type=REPORT_INCIDENT)
响应：{travel_guide, version_lineage, conflicts}

POST /api/guides/{id}/refresh
请求：{expected_guide_version, idempotency_key}
响应：{travel_guide, version_lineage, refreshed_snapshot_id}

GET /api/guides/{id}/export?format=markdown|pdf
P1接口
```

### 13.3 错误码

```text
CONTRACT_MISMATCH
VERSION_CONFLICT
OUT_OF_KNOWLEDGE_COVERAGE
DATA_MISSING
NO_FEASIBLE_PLAN
DATA_EXPIRED
VALIDATION_FAILED
PROVIDER_UNAVAILABLE
```

缺失字段和Provider降级属于正常工作流状态或warning，不作为HTTP错误。

## 14. 状态转换与业务不变量

```text
PARSING → ASKING_CLARIFICATION → RECOMMENDING → WAITING_CONFIRMATION
→ PLANNING → VALIDATING → COMPOSING_GUIDE → PRESENTED
→ REPLANNING → VALIDATING → COMPOSING_GUIDE → PRESENTED
```

不变量：

1. LLM不得输出候选集合外的实体ID。
2. `UNAVAILABLE`资源不得进入计划。
3. `UNKNOWN`关键事实阻止VERIFIED模式发布。
4. `PlanValidationStatus.INVALID`不得生成READY攻略。
5. Mock数据必须进入`DataSnapshot.mock_items`并在前端显示。
6. 锁定节点不得被静默修改或删除。
7. 每次成功修改都生成新计划版本和攻略版本。
8. 总预算只能由`CostItem[]`计算。
9. 行程日期必须完整覆盖旅行日期。
10. 数据不足返回`DATA_MISSING`；有数据但无可行组合返回`NO_FEASIBLE_PLAN`。

## 15. P0/P1能力裁决

详细矩阵见`SCOPE_MATRIX.md`。本文件只声明：

- P0生成完整七部分攻略、保存新版本并支持通用重规划。
- P0允许Mock/固定快照/实时API/混合Provider，但必须标记数据可信状态。
- P0完成住宿区域和人工整理候选，不要求实时库存。
- P0天气用于展示和准备提醒；自动天气触发器为P1，手工报告天气事件可走通用重规划。
- P1包括双目的地真实规划、实时库存/票量、撤回UI、自动事件监控和导出。

## 16. 契约变更规则

1. 新增可选字段需要更新示例和模型。
2. 删除、重命名、改变枚举或不变量必须三人确认。
3. 先修改契约、Pydantic模型和fixtures，再修改业务代码。
4. 所有合法fixture必须通过校验；所有非法fixture必须按预期失败。

## 附录A：资源判别联合类型字段

### VisitPlaceCandidate

在基础字段上增加：`opening_windows, last_entry_at, reservation_required, reservation_method, ticket_cost_item_ids, physical_intensity, indoor, weather_sensitivity, accessibility_tags, crowd_level`。

### LodgingCandidate

增加：`lodging_type, brand, star_level, price_range, rating, review_count, quality_flags, facilities, room_types, check_in_time, check_out_time, nearby_transport, commute_summary, suitable_for, unsuitable_for, booking_url, availability_is_realtime`。

### RestaurantCandidate

增加：`cuisine, specialty_dishes, price_per_person, opening_windows, meal_types, dietary_tags, spicy_level, reservation_required, queue_note, rating, review_count, route_fit_reason`。

### IntercityOption

增加：`mode, origin_station, destination_station, departure_window, arrival_window, in_vehicle_minutes, door_to_door_minutes, price_range, transfer_count, baggage_note, booking_required, booking_advice, risk_flags`。

### PreparationRule

增加：`trigger_type, trigger_condition, category, item_name, instruction, priority, due_at, reason`。
