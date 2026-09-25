/**
 * 契约对象的 TypeScript 镜像（CONTRACTS.md v0.4 / backend/app/schemas/v04）。
 *
 * 说明（handoff/B_交接说明.md）：前端可以用 TypeScript 描述同样的结构，
 * 但**结构变更一律以后端 `backend/app/schemas/` 与 `CONTRACTS.md` 为准**；
 * 这里只做「读得懂后端返回的 JSON」，不新增任何字段，也不复刻校验逻辑。
 *
 * 只镜像前端实际渲染用到的对象，避免变成第二份契约。
 */

export type RunMode = 'DEMO' | 'VERIFIED'
export type PlanValidationStatus = 'PENDING' | 'VALID' | 'INVALID'
export type DataAssuranceStatus = 'VERIFIED' | 'DEGRADED' | 'MOCK' | 'INSUFFICIENT'
export type GuideReadiness = 'READY' | 'READY_WITH_WARNINGS' | 'NOT_READY'
export type GuideLifecycleStatus = 'DRAFT' | 'CONFIRMED' | 'EXECUTING' | 'COMPLETED' | 'OUTDATED'
export type IntensityLevel = 'LOW' | 'MEDIUM' | 'HIGH'
export type DestinationMode = 'UNKNOWN' | 'SINGLE' | 'MULTIPLE'

/** §1.1 金额。`amount` 与 `min_amount`/`max_amount` 互斥且必须有一方。 */
export interface Money {
  amount: number | null
  min_amount: number | null
  max_amount: number | null
  currency: string
}

export interface TimeWindow {
  start_at: string
  end_at: string
}

export interface TravelerComposition {
  adults: number
  children: number
  seniors: number
}

export interface Constraint {
  constraint_id: string
  kind: 'FIXED' | 'NEGOTIABLE_HARD' | 'SOFT'
  field: string
  operator: string
  value: unknown
  priority: number
  source_text: string | null
}

export interface DestinationRequest {
  destination_id: string
  name: string
  desired_days: number | null
  min_days: number | null
  max_days: number | null
  priority: 'LOW' | 'MEDIUM' | 'HIGH'
  fixed: boolean
  user_reason: string | null
}

/** §2.3 正式画像（关键字段必填）。 */
export interface TripProfile {
  session_id: string
  profile_version: number
  departure_city: string
  start_date: string
  end_date: string
  duration_days: number
  timezone: string
  traveler_count: number
  traveler_composition: TravelerComposition
  budget: Money
  budget_flexibility: 'FIXED' | 'NEGOTIABLE'
  pace: 'RELAXED' | 'BALANCED' | 'INTENSE'
  interests: string[]
  must_visit_resource_ids: string[]
  avoidances: string[]
  mobility_constraints: string[]
  dietary_constraints: string[]
  lodging_preferences: string[]
  transport_preferences: string[]
  earliest_day_start: string | null
  latest_day_end: string | null
  destination_mode: DestinationMode
  destination_requests: DestinationRequest[]
  constraints: Constraint[]
}

/** §6 目的地推荐。 */
export interface DestinationRecommendation {
  destination_id: string
  readiness_id: string
  suggested_days: number
  suitable: boolean
  reason: string | null
  tradeoffs: string[]
  risk_flags: string[]
  evidence_ids: string[]
}

/** §8 验证与冲突。 */
export interface RepairOption {
  repair_option_id: string
  action: string
  description: string
  affected_node_ids: string[]
  requires_user_confirmation: boolean
}

export interface Conflict {
  conflict_id: string
  type: string
  severity: 'WARNING' | 'ERROR'
  scope: string
  message: string
  affected_node_ids: string[]
  repair_options: RepairOption[]
  status: string
}

/** §10.2 LangGraph 状态（只存引用，不存业务对象）。 */
export interface PlanState {
  session_id: string
  stage: string
  trip_profile_version: number
  destination_candidate_ids: string[]
  resource_candidate_ids: string[]
  current_plan_id: string | null
  current_plan_version: number | null
  current_guide_id: string | null
  current_guide_version: number | null
  conflict_ids: string[]
  locked_node_ids: string[]
  completed_node_ids: string[]
  active_incidents: string[]
  data_snapshot_id: string | null
  repair_attempts: number
  awaiting_user_input: boolean
}

/** §13 REST 统一信封。 */
export interface WarningItem {
  code: string
  message: string
  details: Record<string, string>
}

export interface ErrorDetail {
  code: string
  message: string
  details: Record<string, string>
}

export interface Envelope<T> {
  ok: boolean
  data: T | null
  warnings: WarningItem[]
  error: ErrorDetail | null
  trace_id: string | null
}

export interface CreateSessionData {
  session_id: string
  state: PlanState
}

/** §13.1 每轮对话的返回体（前端要读的字段都在这里）。 */
export interface SendMessageData {
  stage: string
  assistant_message: string
  trip_profile: TripProfile | null
  destination_candidates: DestinationRecommendation[]
  guide_id: string | null
  conflicts: Conflict[]
  degraded_items: string[]
}

/** §1.2 出行段。 */
export interface TravelLeg {
  leg_id: string
  from_node_id: string
  to_node_id: string
  recommended_mode: string
  alternative_modes: string[]
  depart_at: string
  arrive_at: string
  duration_minutes: number
  distance_km: number
  cost_item_ids: string[]
  congestion_note: string | null
  walking_burden: IntensityLevel
  transfer_count: number
  reason: string
  source: 'MAP_PROVIDER' | 'MANUAL_MATRIX' | 'FAKE'
  is_estimated: boolean
}

export interface CostItem {
  cost_item_id: string
  category: 'INTERCITY' | 'LODGING' | 'LOCAL_TRANSPORT' | 'TICKET' | 'DINING' | 'SHOPPING' | 'OTHER'
  item_ref: string
  unit_price: Money
  quantity: number
  pricing_scope: 'PER_PERSON' | 'PER_GROUP' | 'PER_ROOM' | 'PER_NIGHT' | 'PER_ITEM'
  status: 'KNOWN' | 'ESTIMATED' | 'UNKNOWN'
  paid: boolean
  refundable: boolean | null
  evidence_ids: string[]
}

export interface BudgetSummary {
  currency: string
  total_limit: number
  known_total: number
  estimated_min_total: number
  estimated_max_total: number
  remaining_min: number
  remaining_max: number
  by_category: Record<string, number>
  unknown_cost_item_ids: string[]
}

export interface TripSegment {
  segment_id: string
  destination_id: string
  start_date: string
  end_date: string
  allocated_days: number
}

export interface StaySegment {
  stay_segment_id: string
  check_in_date: string
  check_out_date: string
  lodging_id: string
  lodging_area: string
  is_user_booked: boolean
  locked: boolean
  switch_reason: string | null
}

/** §5 资源候选公共字段（住宿候选用它 + 自己的字段）。 */
export interface LodgingCandidate {
  resource_id: string
  resource_type: 'LODGING'
  destination_id: string
  name: string
  lodging_type: 'STAR_HOTEL' | 'CHAIN' | 'LOCAL_FEATURED' | 'HOSTEL' | 'ECONOMY'
  address: string
  lodging_area: string
  price_range: Money
  rating: number | null
  review_count: number | null
  quality_flags: string[]
  facilities: string[]
  commute_summary: string
  suitable_for: string[]
  unsuitable_for: string[]
  booking_url: string | null
  availability_is_realtime: boolean
  evidence_ids: string[]
}

/** §1.4 城际交通方案。 */
export interface IntercityOption {
  option_id: string
  mode: string
  origin_station: string
  destination_station: string
  departure_window: TimeWindow
  arrival_window: TimeWindow
  door_to_door_minutes: number
  price_range: Money
  transfer_count: number
  baggage_note: string | null
  booking_required: boolean
  booking_advice: string | null
  risk_flags: string[]
  evidence_ids: string[]
}

export interface ArrivalPlan {
  station: string
  first_destination_type: 'LODGING' | 'MEAL' | 'ACTIVITY'
  first_destination_id: string
  local_transport_mode: string
  duration_minutes: number
  estimated_cost: Money
  reason: string
}

export interface ReturnPlan {
  origin_id: string
  departure_station: string
  local_transport_mode: string
  recommended_leave_at: string
  duration_minutes: number
  estimated_cost: Money
  reason: string
}

export interface PreparationItem {
  item_id: string
  category: 'DOCUMENT' | 'BOOKING' | 'CLOTHING' | 'EQUIPMENT' | 'HEALTH' | 'REFRESH'
  title: string
  description: string
  trigger_type: string
  trigger_ref: string | null
  priority: 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL'
  due_at: string | null
  reason: string
  completed: boolean
  evidence_ids: string[]
}

export interface AlternativePlan {
  alternative_plan_id: string
  trigger: string
  affected_node_ids: string[]
  replacement_resource_ids: string[]
  cost_delta: Money
  time_delta_minutes: number
  reason: string
  requires_user_confirmation: boolean
}

// --- 七部分攻略 --------------------------------------------------------------

export interface TripSummarySection {
  destination_names: string[]
  start_date: string
  end_date: string
  duration_days: number
  traveler_count: number
  overall_theme: string
  overall_reason: string
  major_tradeoffs: string[]
}

export interface ArrivalAndDepartureSection {
  recommended_option: IntercityOption
  alternative_options: IntercityOption[]
  arrival_plan: ArrivalPlan
  return_plan: ReturnPlan
}

export interface PreparationSection {
  items: PreparationItem[]
  refresh_before_departure: PreparationItem[]
}

export interface LodgingSection {
  stay_segments: StaySegment[]
  primary_candidates: LodgingCandidate[]
  alternative_candidates: LodgingCandidate[]
}

/** §1.3 展示用节点（与内部 PlanNode 是两个不同对象，禁止混用）。 */
export interface GuideNode {
  node_id: string
  node_type: string
  resource_id: string | null
  name: string
  address: string | null
  start_at: string
  end_at: string
  opening_window: TimeWindow | null
  last_entry_at: string | null
  reservation_required: boolean
  estimated_cost: Money
  reason: string
  tips: string[]
  locked: boolean
  evidence_ids: string[]
}

export interface GuideDay {
  date: string
  day_theme: string
  activity_areas: string[]
  start_location: string
  end_location: string
  nodes: GuideNode[]
  travel_legs: TravelLeg[]
  total_activity_minutes: number
  total_travel_minutes: number
  intensity_level: IntensityLevel
  estimated_cost: Money
  warnings: string[]
  alternative_plan_ids: string[]
}

export interface BudgetAndAlternativesSection {
  budget_summary: BudgetSummary
  alternative_plans: AlternativePlan[]
}

export interface SourcesAndFreshnessSection {
  fact_record_ids: string[]
  evidence_ids: string[]
  degraded_items: string[]
  mock_items: string[]
  unknown_items: string[]
  last_updated: string
}

/** §9 用户最终产物：七部分攻略。 */
export interface TravelGuide {
  guide_id: string
  guide_version: number
  parent_guide_version: number | null
  session_id: string
  run_mode: RunMode
  lifecycle_status: GuideLifecycleStatus
  plan_validation_status: PlanValidationStatus
  data_assurance_status: DataAssuranceStatus
  guide_readiness: GuideReadiness
  timezone: string
  trip_summary: TripSummarySection
  arrival_and_departure: ArrivalAndDepartureSection
  preparation: PreparationSection
  lodging: LodgingSection
  daily_itinerary: GuideDay[]
  budget_and_alternatives: BudgetAndAlternativesSection
  sources_and_freshness: SourcesAndFreshnessSection
  plan_id: string
  plan_version: number
  data_snapshot_id: string
}

// --- B 线内部：对话记录 ------------------------------------------------------

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  stage?: string
  at: string
}
