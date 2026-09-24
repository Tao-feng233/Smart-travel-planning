# 共享数据与接口契约 v0.3

本文件是三条开发线之间的唯一接口标准。字段名使用英文，枚举使用大写英文，面向用户的文字使用中文。示例省份和目的地仅作占位。

## 1. TripProfile

```json
{
  "session_id": "sess_001",
  "departure_city": "上海",
  "start_date": "2026-10-02",
  "end_date": "2026-10-06",
  "traveler_count": 2,
  "traveler_composition": {
    "adults": 2,
    "children": 0,
    "seniors": 0
  },
  "mobility_constraints": [],
  "budget": {
    "amount": 5000,
    "currency": "CNY",
    "flexibility": "NEGOTIABLE"
  },
  "pace": "RELAXED",
  "interests": ["FOOD", "CULTURE", "NATURE"],
  "avoidances": ["HIGH_INTENSITY_HIKING"],
  "fixed_facts": [],
  "hard_constraints": [],
  "soft_preferences": ["少走路", "不想早起"],
  "destination_mode": "UNKNOWN",
  "destination_requests": [],
  "missing_fields": []
}
```

`budget.flexibility`：`FIXED | NEGOTIABLE`。

`destination_mode`：`UNKNOWN | SINGLE | MULTIPLE`。

## 2. KnowledgeCoverage

目的地是否可用于完整攻略由数据覆盖检查决定，不维护人工硬编码名单。

```json
{
  "destination_id": "dest_001",
  "coverage_version": "2026-09-23-v1",
  "destination_profile_status": "AVAILABLE",
  "visit_place_count": 18,
  "visit_place_fact_coverage": 0.9,
  "opening_rule_coverage": 0.85,
  "route_coverage": 0.8,
  "lodging_coverage": 0.75,
  "restaurant_coverage": 0.5,
  "intercity_transport_coverage": 0.6,
  "preparation_rule_coverage": 1.0,
  "missing_capabilities": ["REALTIME_HOTEL_AVAILABILITY"],
  "planning_ready": true,
  "evaluated_at": "2026-09-23T18:00:00+08:00"
}
```

覆盖阈值属于可配置规则，并根据用户天数和攻略要求重新计算。`planning_ready=false`的目的地不得进入完整攻略候选。

## 3. DestinationRequest

```json
{
  "destination_id": "dest_chengdu",
  "name": "成都",
  "desired_days": 3,
  "min_days": 2,
  "max_days": 4,
  "priority": "HIGH",
  "fixed": false,
  "user_reason": "想多体验美食和城市人文"
}
```

## 4. DestinationRecommendation

```json
{
  "destination_id": "dest_chengdu",
  "suggested_days": 3,
  "coverage_version": "2026-09-23-v1",
  "suitable": true,
  "reason": "美食和人文资源丰富，城市内交通相对方便",
  "tradeoffs": ["自然景观比例较低"],
  "risk_flags": ["HOLIDAY_CROWD"],
  "evidence_ids": ["ev_101", "ev_205"]
}
```

LLM不得输出候选集合之外的 `destination_id`。

## 5. ResourceCandidate

```json
{
  "resource_id": "poi_1001",
  "resource_type": "VISIT_PLACE",
  "destination_id": "dest_chengdu",
  "name": "示例景点",
  "latitude": 30.0,
  "longitude": 104.0,
  "categories": ["CULTURE", "INDOOR"],
  "suggested_duration_minutes": 120,
  "estimated_cost": 50,
  "availability": {
    "status": "AVAILABLE",
    "valid_dates": ["2026-10-03", "2026-10-04"],
    "time_windows": [
      {"start": "09:00", "end": "16:30"}
    ],
    "reservation_required": false,
    "reason": null
  },
  "physical_intensity": "LOW",
  "weather_sensitivity": "LOW",
  "evidence_ids": ["ev_301"],
  "source_updated_at": "2026-09-20T10:00:00+08:00",
  "valid_until": "2026-10-10T23:59:59+08:00"
}
```

`resource_type`：`VISIT_PLACE | RESTAURANT | LODGING | LODGING_AREA | TRANSFER_OPTION`。

`availability.status`：`AVAILABLE | CONDITIONAL | UNAVAILABLE | UNKNOWN`。

不同资源类型的详细字段遵循 `TRAVEL_GUIDE_SPEC.md` 中的 `VisitPlace`、`RestaurantCandidate` 和 `LodgingCandidate` 定义。公共字段用于筛选和规划，类型字段用于攻略展示。

## 6. Evidence

```json
{
  "evidence_id": "ev_301",
  "entity_id": "poi_1001",
  "entity_type": "VISIT_PLACE",
  "content": "该区域适合慢节奏步行游览",
  "source_type": "GUIDE",
  "source_ref": "待填写的URL或数据标识",
  "collected_at": "2026-09-23T10:00:00+08:00",
  "valid_until": null,
  "acquisition_status": "UNASSESSED",
  "verification_status": "PENDING"
}
```

`source_type`：`OFFICIAL | AUTHORITY | PLATFORM | GUIDE | MANUAL | DERIVED | MOCK`。

`acquisition_status`：`UNASSESSED | AVAILABLE | LIMITED | UNAVAILABLE | MOCK_ONLY`。

`verification_status`：`PENDING | VERIFIED | REVIEW | REJECTED`。`REJECTED`不得进入LLM上下文，模拟或未验证信息必须显式标记。

## 7. TravelLeg

```json
{
  "leg_id": "leg_01",
  "from_node_id": "node_01",
  "to_node_id": "node_02",
  "recommended_mode": "METRO",
  "alternative_modes": ["TAXI"],
  "depart_time": "11:30",
  "arrive_time": "11:55",
  "duration_minutes": 25,
  "distance_km": 6.4,
  "estimated_cost": 4,
  "congestion_note": "高峰时段打车可能拥堵",
  "walking_burden": "LOW",
  "transfer_count": 1,
  "reason": "地铁时间更稳定",
  "source": "MAP_PROVIDER",
  "is_estimated": false
}
```

本地交通只给出建议方式、耗时、费用、拥堵和步行负担，不承担逐路口导航。`source`：`MAP_PROVIDER | MANUAL_MATRIX | FAKE`。

## 8. ItineraryPlan

```json
{
  "plan_id": "plan_001",
  "session_id": "sess_001",
  "version": 1,
  "status": "VALIDATED",
  "segments": [
    {
      "segment_id": "seg_01",
      "destination_id": "dest_chengdu",
      "start_date": "2026-10-02",
      "end_date": "2026-10-04",
      "allocated_days": 3
    }
  ],
  "stay_segments": [
    {
      "stay_segment_id": "stay_01",
      "start_date": "2026-10-02",
      "end_date": "2026-10-04",
      "lodging_id": "hotel_001",
      "lodging_area": "示例住宿区域",
      "locked": false
    }
  ],
  "days": [
    {
      "date": "2026-10-03",
      "segment_id": "seg_01",
      "stay_segment_id": "stay_01",
      "activity_areas": ["示例文化片区"],
      "nodes": [
        {
          "node_id": "node_01",
          "node_type": "ATTRACTION",
          "resource_id": "poi_1001",
          "start_time": "09:30",
          "end_time": "11:30",
          "locked": false,
          "estimated_cost": 50,
          "reason": "符合人文偏好且与后续地点距离较近",
          "evidence_ids": ["ev_301"]
        }
      ],
      "travel_legs": []
    }
  ],
  "budget": {
    "known_cost": 800,
    "estimated_cost": 1600,
    "unpriced_items": []
  },
  "warnings": [],
  "data_snapshot_id": "snap_001"
}
```

`status`：`DRAFT | VALIDATED | CONFIRMED | EXECUTING | COMPLETED`。

计划节点类型：`ARRIVAL | CHECK_IN | ATTRACTION | MEAL | REST | WALK_AREA | SHOPPING | TRANSFER | LODGING | FREE_TIME`。

## 9. TravelGuide

`TravelGuide`是用户侧最终产物；`ItineraryPlan`是其中的每日行程核心。七部分的详细字段要求见 `TRAVEL_GUIDE_SPEC.md`。

```json
{
  "guide_id": "guide_001",
  "session_id": "sess_001",
  "version": 1,
  "status": "VALIDATED",
  "trip_summary": {
    "destination_names": ["示例目的地"],
    "start_date": "2026-10-02",
    "end_date": "2026-10-06",
    "traveler_count": 2,
    "overall_theme": "轻松的人文与美食之旅",
    "overall_reason": "减少跨区通勤并保留充足休息"
  },
  "arrival_and_departure": {
    "recommended_option": {},
    "alternative_options": [],
    "arrival_plan": {},
    "return_plan": {}
  },
  "preparation": {
    "items": [],
    "refresh_before_departure": []
  },
  "lodging": {
    "stay_segments": [],
    "primary_candidates": [],
    "alternative_candidates": []
  },
  "daily_itinerary": {},
  "budget_and_alternatives": {
    "budget_summary": {},
    "alternative_plans": []
  },
  "sources_and_freshness": {
    "evidence": [],
    "degraded_items": [],
    "unknown_items": [],
    "last_updated": "2026-09-23T18:00:00+08:00"
  }
}
```

`status`：`DRAFT | VALIDATED | CONFIRMED | EXECUTING | COMPLETED | OUTDATED`。

P0前端必须完整渲染七部分；字段无法获得时保留空值并列入`unknown_items`，不得伪造填充。

## 10. Conflict

```json
{
  "conflict_id": "conf_001",
  "type": "TIME_WINDOW",
  "severity": "ERROR",
  "scope": "DAY",
  "message": "预计抵达时间晚于最晚入园时间",
  "affected_node_ids": ["node_01", "node_02"],
  "repair_options": [
    {
      "action": "REORDER_NODES",
      "description": "交换两个景点顺序",
      "requires_user_confirmation": false
    }
  ]
}
```

`severity`：`WARNING | ERROR`。`ERROR`不得进入已验证状态。

## 11. PlanState

```json
{
  "session_id": "sess_001",
  "stage": "VALIDATING",
  "profile": {},
  "destination_candidates": [],
  "resource_candidates": [],
  "current_plan": {},
  "current_guide": {},
  "conflicts": [],
  "locked_node_ids": [],
  "completed_node_ids": [],
  "change_history": [],
  "data_snapshot_id": "snap_001",
  "repair_attempts": 0,
  "awaiting_user_input": false
}
```

## 12. MCP工具契约

### `search_planning_ready_destinations`

输入：`query, travel_dates, duration_days, traveler_constraints, top_k?`

输出：通过KnowledgeCoverage检查的目的地候选、coverage_version和用于后续RAG检索的destination_id。LLM不能绕过该结果增加新目的地。

### `search_travel_knowledge`

输入：`query, province, destination_ids?, resource_type?, top_k?`

输出：`Evidence[]`，每项必须包含 `evidence_id, entity_id, content, source, updated_at`。

### `get_place_facts`

输入：`resource_ids[], start_date, end_date`

输出：对应资源的结构化事实及有效期。

### `get_place_availability`

输入：`resource_id, date, requested_time_window?`

输出：`status, time_windows, reservation_required, reason, evidence_ids`。

### `get_route`

输入：`origin, destination, departure_time?, mode?`

输出：`duration_minutes, distance_km, estimated_cost, source, is_estimated`。

### `get_weather`

输入：`destination_id, date`

输出：`condition, temperature_range, precipitation_probability, source, is_forecast`。

## 13. UserAction与ChangeRequest

用户选择目的地、确认攻略、修改攻略和报告突发情况属于不同动作，不全部混入ChangeRequest。

```json
{
  "action_type": "MODIFY_GUIDE",
  "session_id": "sess_001",
  "guide_id": "guide_001",
  "raw_text": "第二天太累了，下午少安排一个景点",
  "payload": {
    "change_type": "LOWER_INTENSITY",
    "scope_hint": "DAY",
    "day_date": "2026-10-03",
    "target_node_ids": []
  }
}
```

`action_type`：`SELECT_DESTINATION | CONFIRM_GUIDE | MODIFY_GUIDE | REPORT_INCIDENT`。

`change_type`仅在`MODIFY_GUIDE`时使用：`REMOVE_NODE | REPLACE_NODE | ADD_FIXED_NODE | LOWER_INTENSITY | CHANGE_DATE | CHANGE_BUDGET | CHANGE_PACE | CHANGE_LODGING`。

`scope_hint`：`NODE | DAY | STAY_SEGMENT | TRIP_SEGMENT | WHOLE_GUIDE`。B负责提取建议范围，C根据真实依赖关系确定最终重规划范围。

## 14. REST接口建议

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/sessions` | 创建会话 |
| POST | `/api/sessions/{id}/messages` | 输入自然语言并推进LangGraph |
| GET | `/api/sessions/{id}` | 获取当前PlanState |
| GET | `/api/guides/{id}` | 获取七部分TravelGuide |
| POST | `/api/guides/{id}/confirm` | 用户确认攻略并锁定关键内容 |
| POST | `/api/guides/{id}/modify` | 提交攻略或行程修改 |
| POST | `/api/guides/{id}/incident` | 报告突发情况并重规划 |
| POST | `/api/guides/{id}/refresh` | 刷新动态数据、再验证并生成新版本 |
| GET | `/api/guides/{id}/export` | P1导出Markdown或PDF |

前端默认通过消息接口推进流程，其他接口用于明确动作。

## 15. 契约变更规则

1. 新增可选字段可以向后兼容。
2. 删除字段、重命名字段和改变枚举必须三人确认。
3. 任何契约变更先修改本文件和示例JSON，再修改代码。
4. 各模块测试使用本文件中的示例作为fixture基础。
