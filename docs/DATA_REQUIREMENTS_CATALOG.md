# 旅游攻略数据需求总目录 v0.1

本文件列出生成七部分TravelGuide所需的全部数据类别、具体字段、用途、优先级和缺失时的处理方式。它描述“需要什么数据”，不预设“必须从哪家平台获取”。实际数据源由独立调研填写 `DATA_SOURCE_ASSESSMENT_TEMPLATE.md`。

## 1. 优先级定义

```text
P0_REQUIRED
缺失后无法生成可执行攻略，或必须把相关内容标为未知

P0_OPTIONAL
第一版尽量收集；缺失时允许降级，但必须显式说明

P1
后续优化，不阻塞第一版闭环
```

## 2. 数据类别总览

| 类别 | 主要作用 | 优先级 |
|---|---|---|
| 知识覆盖元数据 | 判断某目的地是否能生成完整攻略 | P0_REQUIRED |
| 目的地与区域 | 目的地推荐、整体路线和区域聚类 | P0_REQUIRED |
| 游玩地点 | 生成每天多个活动节点 | P0_REQUIRED |
| 开放、门票与预约 | 前置过滤和时间窗验证 | P0_REQUIRED |
| 城际交通 | 决定怎么抵达和离开 | P0_REQUIRED或降级 |
| 本地路线 | 计算节点间交通和通勤 | P0_REQUIRED |
| 住宿 | 决定住哪里和每日起终点 | P0_REQUIRED |
| 餐饮 | 插入用餐时间和位置 | P0_OPTIONAL，可降级 |
| 天气与环境 | 准备清单、室内外安排和重规划 | P0_OPTIONAL，可模拟 |
| 人流与日历 | 推荐时间段和避峰 | P0_OPTIONAL |
| 行前准备规则 | 生成证件、衣物和装备清单 | P0_REQUIRED，可人工维护 |
| 预算与参考价格 | 预算验证和费用汇总 | P0_REQUIRED |
| RAG知识与证据 | 支持LLM比较、解释和引用 | P0_REQUIRED |
| 用户需求 | 个性化筛选、排序和约束 | P0_REQUIRED |
| 计划与版本状态 | 修改、锁定和局部重规划 | P0_REQUIRED |
| 应急与公共服务 | 安全和突发处理 | P1 |

## 3. 知识覆盖元数据

目的地不依靠人工写死的支持名单，而是由数据覆盖状态决定是否 `planning_ready`。

```text
KnowledgeCoverage
├── destination_id
├── coverage_version
├── destination_profile_status
├── visit_place_count
├── visit_place_fact_coverage
├── opening_rule_coverage
├── route_coverage
├── lodging_coverage
├── restaurant_coverage
├── intercity_transport_coverage
├── preparation_rule_coverage
├── freshness_summary
├── missing_capabilities[]
├── planning_ready
└── evaluated_at
```

### 规划就绪判断

应根据当前用户的旅行天数和要求动态判断，而不是固定“有10个景点就支持”。至少需要：

- 存在目的地和区域基本资料。
- 有足够的可用游玩地点覆盖用户天数，并保留替代项。
- 核心地点具备开放时间、建议时长、位置和基本费用。
- 候选地点之间有路线数据或可用人工矩阵。
- 至少有住宿区域和可靠住宿候选。
- 能给出抵达方式，或明确要求用户提供已订交通。
- 缺失的餐饮、天气等能力有明确降级方案。

`planning_ready=false`时，系统不得生成“已验证”的完整攻略。

## 4. 目的地数据

用于目的地推荐、停留天数建议和整体路线说明。

| 字段 | 含义 | 优先级 |
|---|---|---|
| destination_id | 内部唯一ID | P0_REQUIRED |
| name/aliases | 名称和常用别名 | P0_REQUIRED |
| administrative_area | 省、市、区或旅行区域 | P0_REQUIRED |
| center_coordinate | 中心坐标 | P0_REQUIRED |
| destination_type | 城市、山区、海滨、古镇等 | P0_REQUIRED |
| experience_tags | 美食、人文、自然、亲子、夜生活等 | P0_REQUIRED |
| suitable_for | 适合人群 | P0_REQUIRED |
| unsuitable_for | 反适合人群 | P0_REQUIRED |
| recommended_min/max_days | 建议停留天数范围 | P0_REQUIRED |
| typical_pace | 典型旅行节奏 | P0_OPTIONAL |
| consumption_level | 大致消费水平 | P0_REQUIRED |
| climate_and_season | 季节与气候特点 | P0_OPTIONAL |
| peak_periods | 旺季、节假日和特殊高峰 | P0_OPTIONAL |
| major_risks | 高海拔、极端天气、拥挤等 | P0_OPTIONAL |
| arrival_hubs | 主要机场、车站和客运枢纽 | P0_REQUIRED |
| knowledge_evidence_ids | 认知知识证据 | P0_REQUIRED |

## 5. 游玩区域数据

用于把同一区域的多个地点安排在一起，避免跨区往返。

| 字段 | 含义 | 优先级 |
|---|---|---|
| area_id | 区域ID | P0_REQUIRED |
| destination_id | 所属目的地 | P0_REQUIRED |
| name | 区域名称 | P0_REQUIRED |
| boundary_or_center | 边界或中心坐标 | P0_REQUIRED |
| area_character | 历史街区、商业区、自然片区等 | P0_REQUIRED |
| experience_tags | 区域体验标签 | P0_REQUIRED |
| typical_duration | 建议半天/一天等 | P0_OPTIONAL |
| walking_burden | 区域内部步行强度 | P0_OPTIONAL |
| suitable_time | 适合上午、下午或夜间 | P0_OPTIONAL |
| transit_access | 地铁、公交、打车便利性 | P0_OPTIONAL |
| nearby_place_ids | 区域内地点列表 | P0_REQUIRED |

## 6. 游玩地点数据

包括景点、博物馆、公园、历史街区、商圈、步行街、观景点、夜游、体验项目等。

### 身份与位置

```text
resource_id
name
aliases[]
place_type
destination_id
area_id
address
latitude/longitude
entrance_or_meeting_point
```

### 体验与适配

```text
short_description
experience_tags[]
suitable_for[]
unsuitable_for[]
recommended_season
recommended_time_of_day
suggested_duration_minutes
physical_intensity
walking_distance_or_steps
indoor/outdoor
weather_sensitivity
accessibility_tags[]
child_friendly
senior_friendly
photo_value/night_view/local_character等认知标签
```

### 运营事实

```text
opening_rules
closed_weekdays
special_closed_dates
open_time
last_entry_time
close_time
reservation_required
reservation_method
reservation_lead_time
ticket_required
ticket_price_rules
identity_document_required
capacity_or_time_slot_rules
```

### 现场信息

```text
estimated_queue_pattern
crowd_pattern
internal_transport
recommended_entrance
luggage_or_storage_info
toilet/rest_area_info
food_availability_nearby
special_notices
```

### 证据与质量

```text
evidence_ids[]
source_updated_at
valid_until
verification_status
```

P0必须保证：名称、类型、位置、开放规则、建议时长、费用、预约、体力、室内外和证据状态。其他现场细节可列P1。

## 7. 门票、价格和人群政策

价格不能只保存一个数字，因为可能存在成人、学生、老人、儿童和节假日差异。

```text
PriceRule
├── resource_id
├── item_name
├── audience_type
├── min_age/max_age
├── date_type              工作日/节假日/旺季
├── amount
├── currency
├── included_items
├── excluded_items
├── valid_from/valid_to
├── purchase_channel
└── evidence_ids[]
```

## 8. 城际交通数据

用于回答“怎么去、怎么回来”，不要求P0完成真实购票。

```text
IntercityOption
├── option_id
├── mode                   FLIGHT/HIGH_SPEED_RAIL/TRAIN/BUS/INTERCITY_METRO/SELF_DRIVE
├── origin_city
├── origin_station
├── destination_city
├── destination_station
├── typical_departure_window
├── typical_arrival_window
├── in_vehicle_minutes
├── door_to_door_minutes
├── price_range
├── transfer_count
├── frequency_summary
├── booking_required
├── booking_lead_time
├── baggage_or_checkin_rules
├── service_calendar
├── real_time_availability
├── suitable_for[]
├── risk_flags[]
└── evidence_ids[]
```

### P0最低要求

- 可用交通方式。
- 主要出发/到达枢纽。
- 典型门到门耗时。
- 价格区间。
- 预订提示。
- 到达后与住宿或首个活动的衔接。

拿不到具体班次时不得虚构车次号。

## 9. 本地路线和交通数据

用于连接酒店、景点、餐厅和车站。

```text
RouteOption
├── origin_id/origin_coordinate
├── destination_id/destination_coordinate
├── mode                   WALK/METRO/BUS/TAXI/BIKE/OTHER
├── duration_minutes
├── distance_km
├── estimated_cost
├── walking_minutes
├── transfer_count
├── congestion_level
├── service_time_window
├── accessibility_note
├── source
├── is_estimated
└── collected_at
```

P0不需要逐路口导航。系统根据用户体力、时间、预算和拥堵选择建议方式，用户实际导航可跳转地图应用。

## 10. 住宿数据

目标是推荐相对可靠、符合用户预算和路线的住宿，而不是只找最低价。

### 基本信息

```text
lodging_id
name
lodging_type           STAR_HOTEL/CHAIN/LOCAL_FEATURED/HOSTEL/ECONOMY
brand
star_level
address
latitude/longitude
lodging_area
contact_or_booking_url
```

### 价格与入住

```text
price_range
price_date_scope
room_types[]
occupancy_limit
check_in_time/check_out_time
deposit_rules
cancellation_summary
availability_status
```

### 质量与设施

```text
rating
review_count
quality_flags[]        卫生、隔音、服务、位置、陈旧等
facilities[]           空调、洗衣、早餐、电梯、停车等
accessibility
family_friendly
security_notes
reliability_level
```

### 路线适配

```text
nearby_transit[]
station_distance
food_convenience
commute_to_activity_areas
arrival_hub_access
return_hub_access
suitable_for[]
unsuitable_for[]
```

### 证据

```text
source_updated_at
evidence_ids[]
availability_is_real_time
```

P0建议准备一个主推荐和若干备选；没有实时库存时只写“候选”，不得写“可订”。

## 11. 餐厅数据

P0先解决“路线附近在合适时间吃什么”，更深的评价聚合后续优化。

```text
restaurant_id
name
destination_id/area_id
address
latitude/longitude
cuisine
specialty_dishes[]
price_per_person
opening_hours
meal_types[]
dietary_tags[]         素食、清真、过敏等
spicy_level
reservation_required
queue_pattern
rating/review_count
environment_tags[]
suitable_for[]
route_fit_tags[]
source_updated_at
evidence_ids[]
```

### 缺失时降级

- 有位置、营业时间和人均：可插入具体店铺。
- 只有区域和菜系：推荐用餐区域及餐饮类型。
- 无可靠数据：在攻略中标记餐饮待确认，不由LLM虚构店铺。

## 12. 天气与环境数据

```text
destination_id/coordinate
date/time
weather_condition
temperature_min/max
feels_like
precipitation_probability
rainfall
wind
humidity
visibility
severe_weather_alerts[]
sunrise/sunset
forecast_issued_at
forecast_valid_until
```

相关静态环境数据：

```text
altitude
seasonal_temperature_range
temperature_difference
sun_exposure
water_activity_risk
terrain_type
```

天气用于室内外排序、衣物装备、出发前刷新和动态重规划，不只是展示天气卡片。

## 13. 日历、人流和活动数据

```text
date
weekday
is_public_holiday
holiday_name
school_holiday_or_vacation
peak_season
local_event
place_id/area_id
historical_time_slot
historical_crowd_level
reservation_tightness
prediction_level
prediction_inputs[]
```

只输出 `LOW/MEDIUM/HIGH/EXTREME` 等级及原因，不输出缺乏依据的精确人数。

## 14. 行前准备规则

准备信息采用规则库，可人工整理，不依赖LLM常识自由发挥。

```text
PreparationRule
├── rule_id
├── trigger_type          WEATHER/ACTIVITY/TERRAIN/ALTITUDE/TRAVELER/PLACE
├── trigger_condition
├── item_category         DOCUMENT/BOOKING/CLOTHING/EQUIPMENT/HEALTH/REFRESH
├── item_name
├── instruction
├── priority              REQUIRED/RECOMMENDED/OPTIONAL
├── reason
└── evidence_ids[]
```

示例触发：山区低温、昼夜温差、涉水活动、长距离步行、雨天、强日晒、老人儿童同行、预约需身份证件。

## 15. 预算和费用数据

```text
CostItem
├── category              INTERCITY/LODGING/LOCAL_TRANSPORT/TICKET/DINING/SHOPPING/OTHER
├── item_ref
├── amount_or_range
├── currency
├── per_person_or_group
├── quantity
├── status                KNOWN/ESTIMATED/UNKNOWN
├── valid_at
└── evidence_ids[]
```

还需要：用户总预算、分项偏好、机动预算比例、已付款项目和不可退改费用。

## 16. RAG知识和证据数据

RAG只提供项目知识库中的认知资料，不直接代替开放时间、路线等结构化事实。

```text
EvidenceDocument
├── evidence_id
├── entity_id
├── entity_type
├── document_type          OFFICIAL_INTRO/GUIDE/REVIEW_SUMMARY/POLICY/NOTICE
├── title
├── content
├── source_type
├── source_ref
├── published_at
├── collected_at
├── valid_until
├── verification_status
├── destination_id
├── area_id
├── tags[]
└── chunk_version
```

进入LLM上下文时必须保留 `entity_id` 和 `evidence_id`。LLM只能比较检索结果中的实体。

## 17. 用户需求数据

这些数据由对话获取，不需要外部调研，但必须进入结构化契约。

```text
出发地
日期/天数
人数和同行者组成
预算及是否可协商
兴趣和旅行节奏
体力、步行和无障碍限制
饮食限制
住宿偏好
交通偏好
早起/晚归接受度
必去和排斥项
已经预订的交通、住宿、门票
固定和可协商硬约束
软偏好
```

## 18. 计划、执行和版本状态

```text
session_id
TripProfile版本
TravelGuide版本
ItineraryPlan版本
当前LangGraph阶段
locked_node_ids
completed_node_ids
current_time/current_location
active_incidents[]
change_history[]
conflicts[]
repair_history[]
data_snapshot_id
```

这些数据使局部重规划能够保留已经完成、已经预约和用户锁定的内容。

## 19. 应急与公共服务数据（P1）

```text
emergency_contacts
nearby_hospitals
police_or_service_points
pharmacies
luggage_storage
public_toilets
accessible_facilities
tourist_service_centers
```

如未收集，不应由LLM自行生成地址或电话。

## 20. 每条外部数据共同需要的质量字段

```text
source_type
source_ref
collected_at
valid_until
acquisition_status
verification_status
raw_snapshot_ref
normalization_version
notes
```

## 21. 推荐的数据收集批次

### 批次一：形成最小完整攻略

- 目的地、区域和游玩地点。
- 开放、预约、票价和建议时长。
- 住宿区域和可靠住宿候选。
- 本地路线或人工时间矩阵。
- 抵达方式和主要交通枢纽。
- 行前准备规则。
- 基础费用。

### 批次二：提升舒适度

- 具体餐厅。
- 天气。
- 人流与节假日。
- 更多住宿和质量信息。
- 更多路线方式和拥堵信息。

### 批次三：提高实时性和覆盖

- 实时班次、票价和库存。
- 临时关闭和活动。
- 酒店实时库存、房型和退改。
- 餐厅排队、预约和菜单。
- 应急公共服务。

## 22. 调研交付标准

数据调研不能只回答“某API可以用”，必须为每类数据提供：

1. 当前可访问的候选来源和官方文档链接。
2. 实际可返回字段，与本目录字段逐项对照。
3. 鉴权、申请、额度、费用和调用限制。
4. 使用、缓存、展示和抓取限制。
5. 数据覆盖范围、更新时间和稳定性。
6. 最小请求/响应示例或截图证据。
7. 推荐Provider方案。
8. 失败后的人工数据或fixture降级方案。

