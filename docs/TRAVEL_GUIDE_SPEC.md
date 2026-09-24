# 定制可执行旅游攻略规格 v0.2

本文件定义用户最终获得的 `TravelGuide` 应包含什么、每部分需要收集和结构化哪些数据，以及第一版必须做到什么。具体外部数据源尚未确定的字段可以先使用fixture或模拟Provider，但不得伪装成已核验事实。

## 1. 最终目标

用户确定想去的城市或旅行区域后，系统应尽量替用户完成信息搜集、比较、路线组合和风险检查，使用户按照攻略即可完成旅行，不必再自行把景点、住宿、餐饮和交通重新拼接。

这里的“单目的地”指一个城市或旅行区域，不是只安排一个景点。一个目的地内部必须支持多个游玩区域和多个游玩地点；多目的地是跨城市或跨旅行区域的后续扩展。

系统不能保证所有现实情况永远不变，因此攻略必须把需要预约、需要刷新和无法确认的项目明确列出，并在变化后支持重规划。

## 2. 七部分攻略结构

| 部分 | 用户要解决的问题 | P0要求 |
|---|---|---|
| 旅行总览 | 这次旅行整体怎么安排 | 必须 |
| 抵达与离开 | 怎么去、怎么回来、到站后怎么办 | 必须 |
| 行前准备 | 出发前需要带什么、订什么、确认什么 | 必须 |
| 住宿方案 | 住哪里、是否换住处、为什么 | 必须 |
| 每日详细行程 | 每天从起床到回住处具体做什么 | 必须 |
| 预算与备用方案 | 花多少钱、出问题怎么替换 | 必须 |
| 来源与更新时间 | 哪些信息可靠、哪些需要复核 | 必须 |

## 3. 第一部分：旅行总览

### 用户看到的内容

- 出发地、日期、人数和同行者情况。
- 旅行目的地和总天数。
- 旅行节奏、核心兴趣、必去和排斥项。
- 整体路线：在哪些区域活动、是否换住宿。
- 推荐方案的总体理由和主要取舍。

### 需要结构化的数据

```text
guide_id
version
status
departure_city
start_date
end_date
traveler_count
traveler_composition       成人/老人/儿童等
mobility_constraints       体力、步行、无障碍限制
budget_amount
budget_flexibility
pace
interests[]
must_visit[]
avoidances[]
destination_requests[]
trip_segments[]
overall_theme
overall_reason
major_tradeoffs[]
```

### 数据来源

- 用户对话和 `TripProfile`。
- 目的地推荐结果。
- 经过验证的行程计划。

## 4. 第二部分：抵达与离开

### 用户看到的内容

- 推荐高铁、普通火车、飞机、长途客运或其他可用方式。
- 推荐理由：总耗时、价格、舒适度、出发地距离和到达后的衔接。
- 建议出发和到达时间范围。
- 到站/机场后先去住宿、吃饭还是先游玩。
- 返程方式和最晚需要离开住宿地的时间。
- 主方案和至少一个备选方案。

### 需要结构化的数据

```text
IntercityOption
├── mode                    高铁/火车/飞机/客运/跨市轨道等
├── origin_station
├── destination_station
├── departure_window
├── arrival_window
├── in_vehicle_minutes
├── door_to_door_minutes
├── estimated_cost
├── transfer_count
├── baggage_or_checkin_note
├── booking_required
├── latest_booking_advice
├── suitability_reason
├── risk_flags[]
└── evidence_ids[]

ArrivalPlan
├── arrival_station
├── first_destination_type  HOTEL/MEAL/ACTIVITY
├── first_destination_id
├── local_transport_mode
├── duration_minutes
├── estimated_cost
└── reason
```

### P0与后续优化

- P0：给出交通方式、时间和价格区间、到达后的第一步安排。
- P1：接入具体班次、实时价格、余票和正规平台跳转。
- 无实时班次时不得生成虚构车次，只能提供方式和时间范围。

## 5. 第三部分：行前准备

### 用户看到的内容

- 证件和预约清单。
- 服装、鞋、雨具和常用物品。
- 与活动相关的特殊准备。
- 出发前24～48小时需要刷新的项目。

例如：

- 山区温差较大，建议携带保暖外套。
- 涉水活动可能弄湿衣物，建议携带备用衣物和防水袋。
- 长距离步行建议穿适合行走的鞋。
- 某景点需要提前预约或携带身份证件。

### 需要结构化的数据

```text
PreparationItem
├── item_id
├── category                DOCUMENT/BOOKING/CLOTHING/EQUIPMENT/HEALTH/REFRESH
├── title
├── description
├── trigger_type            WEATHER/ACTIVITY/PLACE/TRAVELER/GENERAL
├── trigger_ref
├── priority                REQUIRED/RECOMMENDED/OPTIONAL
├── due_time
├── reason
├── completed
└── evidence_ids[]
```

### 数据来源

- 用户身体和同行者条件。
- 景点活动标签和装备要求。
- 天气、海拔、温差和季节信息。
- 官方预约和入园规则。
- 已整理的准备规则库。

## 6. 第四部分：住宿方案

### 用户看到的内容

- 每个日期住在哪里。
- 是否需要中途更换住宿。
- 一个主推荐和若干备选。
- 为什么适合用户：价格、质量、交通、周边餐饮和安全便利。
- 哪些信息需要用户在预订平台再次确认。

### 住宿类别

数据采集尽量覆盖：

- 星级酒店。
- 可靠连锁酒店。
- 当地有名或有特色的酒店/民宿。
- 青年旅舍和经济型住宿。

### 需要结构化的数据

```text
LodgingCandidate
├── lodging_id
├── name
├── lodging_type            STAR_HOTEL/CHAIN/LOCAL_FEATURED/HOSTEL/ECONOMY
├── brand
├── star_level
├── address
├── latitude
├── longitude
├── price_range
├── rating
├── review_count
├── quality_flags[]         卫生/隔音/服务/位置等已知标签
├── facilities[]
├── room_types[]
├── check_in_time
├── check_out_time
├── nearby_transport[]
├── nearby_food_score
├── commute_summary
├── suitable_for[]
├── unsuitable_for[]
├── booking_url
├── availability_status
├── source_updated_at
└── evidence_ids[]

StaySegment
├── stay_segment_id
├── start_date
├── end_date
├── lodging_id
├── lodging_area
├── is_user_booked
├── locked
└── switch_reason
```

### 推荐规则

- 先排除明显不满足预算、人数、位置和基本质量要求的住宿。
- LLM基于用户偏好比较可行候选，解释价格、可靠性和通勤取舍。
- 默认尽量少换住宿；只有用户要求、跨区域行程明显受益或已经预订时才安排换住处。
- 无实时库存时只能写“推荐候选”，不能写“当前可订”。

### P0与后续优化

- P0：住宿区域 + 经过整理的具体住宿候选；一个主推荐和备选。
- P1：实时房型、库存、退改政策和价格跳转。

## 7. 第五部分：每日详细行程

这是攻略的核心。每个旅行日应从当天起点开始，安排多个游玩地点、餐饮、休息和回住宿地的过程。

### 不是“一个目的地只去一个景点”

规划器需要先形成游玩区域，再从区域内选择多个适合用户的地点。例如一个城市内可以包含历史街区、博物馆、公园、商圈、夜游和当地体验，并根据地理位置组合，而不是只推荐一个知名景点。

### 每日数据

```text
DayPlan
├── date
├── segment_id
├── stay_segment_id
├── day_theme
├── activity_areas[]
├── start_location
├── end_location
├── nodes[]
├── travel_legs[]
├── total_activity_minutes
├── total_travel_minutes
├── intensity_level
├── estimated_cost
├── warnings[]
└── backup_nodes[]
```

### 计划节点

```text
PlanNode
├── node_id
├── node_type              ARRIVAL/CHECK_IN/ATTRACTION/MEAL/REST/WALK_AREA/SHOPPING/FREE_TIME/LODGING
├── resource_id
├── start_time
├── end_time
├── duration_minutes
├── address
├── opening_window
├── last_entry_time
├── reservation_required
├── estimated_cost
├── reason
├── tips[]
├── locked
└── evidence_ids[]
```

### 本地交通

每两个需要移动的节点之间保存：

```text
TravelLeg
├── from_node_id
├── to_node_id
├── recommended_mode       WALK/METRO/BUS/TAXI/OTHER
├── alternative_modes[]
├── duration_minutes
├── distance_km
├── estimated_cost
├── congestion_note
├── walking_burden
├── transfer_count
├── reason
└── is_estimated
```

攻略只需要告诉用户建议步行、地铁、公交或打车及理由，不负责提供逐路口导航。真正导航可以交给地图应用。

### 景点与游玩地点数据

```text
VisitPlace
├── resource_id
├── name
├── place_type
├── activity_area
├── address/coordinates
├── opening_rules
├── last_entry_time
├── reservation_rules
├── ticket_price
├── suggested_duration
├── suitable_for[]
├── unsuitable_for[]
├── physical_intensity
├── indoor
├── weather_sensitivity
├── crowd_pattern
├── experience_tags[]
└── evidence_ids[]
```

### 餐饮数据

```text
RestaurantCandidate
├── restaurant_id
├── name
├── address/coordinates
├── cuisine
├── specialty_dishes[]
├── price_per_person
├── opening_hours
├── meal_types[]
├── dietary_tags[]
├── spicy_level
├── reservation_required
├── queue_note
├── rating/review_count
├── suitable_for[]
├── route_fit_reason
├── source_updated_at
└── evidence_ids[]
```

### 餐饮P0与后续优化

- P0：根据已有餐厅信息推荐并插入用餐时间，至少考虑位置、营业时间、价格、菜系和饮食限制。
- 数据不足时：推荐用餐区域和餐饮类型，同时明确没有可靠具体店铺数据。
- P1：补充特色菜、排队、预约、菜单、评论聚合和更丰富备选。

## 8. 第六部分：预算与备用方案

### 预算数据

```text
BudgetSummary
├── total_limit
├── intercity_transport
├── lodging
├── local_transport
├── tickets
├── dining
├── shopping
├── contingency
├── known_cost
├── estimated_cost
├── unpriced_items[]
└── remaining_budget
```

所有金额必须标识：

- `KNOWN`：已知或已预订。
- `ESTIMATED`：估算。
- `UNKNOWN`：无法确定。

### 备用方案数据

```text
AlternativePlan
├── trigger                  RAIN/LATE_START/CLOSURE/CROWD/USER_TIRED/RESTAURANT_UNAVAILABLE
├── affected_node_ids[]
├── replacement_nodes[]
├── cost_delta
├── time_delta
├── reason
└── requires_user_confirmation
```

P0至少完整支持一种突发情况的局部重规划，其他情况可以先生成结构化备选说明。

## 9. 第七部分：来源与更新时间

### 统一事实记录

```text
FactRecord
├── entity_id
├── fact_type
├── value
├── source_type
├── source_ref
├── collected_at
├── valid_until
├── acquisition_status
├── verification_status
└── notes
```

### 数据获取状态

外部数据尚未验证时使用：

```text
UNASSESSED    尚未验证
AVAILABLE     可稳定获取
LIMITED       可获取但不完整或有限制
UNAVAILABLE   无法使用
MOCK_ONLY     当前只有模拟数据
```

### 来源类型

```text
OFFICIAL      景区、交通或商家官方来源
AUTHORITY     政府、公共机构
PLATFORM      地图、天气、票务、住宿或餐饮平台
GUIDE         攻略、游记和评论
MANUAL        人工整理并保留原始引用
DERIVED       系统计算或预测
MOCK          演示数据
```

不同事实允许使用不同来源，不要求所有内容都来自同一类来源。任何模拟、估算、预测或过期信息必须在攻略中显式标记。

## 10. P0、P1和结构预留

### P0必须完成

- 单个旅行目的地的完整攻略。
- 一个目的地内多个游玩区域和多个游玩地点。
- 抵达方式建议及到站后第一步安排。
- 行前准备清单。
- 住宿区域和具体住宿候选。
- 每日景点、基础餐饮、本地交通、休息和回住宿地安排。
- 预算、来源、风险和一种动态重规划。
- Vue完整攻略页面。

### P1可优化

- 双目的地真实规划。
- 更丰富餐厅数据和评论分析。
- 实时酒店库存、房型和退改。
- 具体车次/航班和票价。
- 多种突发情况重规划。
- Markdown/PDF导出和地图可视化。

### 从P0就必须保留的扩展结构

- `destination_requests[]`，即使只有一个目的地。
- `trip_segments[]`，P0长度为1。
- `stay_segments[]`，允许未来表达换住宿。
- `travel_legs[]`，支持本地和未来跨目的地移动。
- 每个DayPlan保存`segment_id`和`stay_segment_id`。

## 11. 数据收集顺序

建议先按“能否完成攻略”而不是按“资料最多”收集：

1. 目的地和游玩区域。
2. 核心游玩地点的坐标、开放和建议时长。
3. 住宿区域和可靠住宿候选。
4. 地点间路线或人工时间矩阵。
5. 抵达方式和到站衔接。
6. 行前准备规则。
7. 基础餐厅候选。
8. 天气、人流和动态信息。

成员A应把每一类数据标记为 `UNASSESSED/AVAILABLE/LIMITED/UNAVAILABLE/MOCK_ONLY`，验证后再决定真实接入还是使用fixture。

