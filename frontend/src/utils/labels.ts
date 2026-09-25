/**
 * 枚举值 → 中文文案。
 *
 * 只做"翻译"，**不新增枚举取值**；契约里的 `Literal` 才是唯一取值来源
 * （`backend/app/schemas/v04/models.py`）。遇到未收录的值原样回显，
 * 这样后端扩枚举时前端不会显示成空白。
 */

const STAGE: Record<string, string> = {
  CREATED: '会话已创建',
  PARSING_REQUEST: '正在理解你的需求',
  CHECKING_FIELDS: '正在检查信息完整性',
  ASKING_CLARIFICATION: '需要你补充信息',
  RETRIEVING_DESTINATIONS: '正在检索目的地',
  RECOMMENDING_DESTINATIONS: '正在推荐目的地',
  FETCHING_RESOURCES: '正在获取资源候选',
  FILTERING_RESOURCES: '正在做可用性过滤',
  AWAITING_DESTINATION_CONFIRMATION: '等待你确认目的地',
  INSUFFICIENT_DATA: '知识库暂无覆盖',
  PLANNING: '正在编排行程',
  VALIDATING: '正在验证计划',
  REPAIRING: '正在修复冲突',
  READY: '攻略已就绪',
}

const NODE_TYPE: Record<string, string> = {
  ARRIVAL: '抵达',
  CHECK_IN: '入住',
  ATTRACTION: '景点',
  MEAL: '用餐',
  REST: '休息',
  WALK_AREA: '街区漫步',
  SHOPPING: '购物',
  LODGING: '住宿',
  FREE_TIME: '自由时间',
}

const INTENSITY: Record<string, string> = { LOW: '轻松', MEDIUM: '适中', HIGH: '紧凑' }

const MODE: Record<string, string> = {
  HIGH_SPEED_RAIL: '高铁',
  TRAIN: '火车',
  FLIGHT: '飞机',
  COACH: '大巴',
  SELF_DRIVE: '自驾',
  METRO: '地铁',
  BUS: '公交',
  TAXI: '出租车/网约车',
  WALK: '步行',
  BICYCLE: '骑行',
  FERRY: '轮渡',
  OTHER: '其他',
}

const COST_CATEGORY: Record<string, string> = {
  INTERCITY: '城际交通',
  LODGING: '住宿',
  LOCAL_TRANSPORT: '市内交通',
  TICKET: '门票',
  DINING: '餐饮',
  SHOPPING: '购物',
  OTHER: '其他',
}

const PRICING_SCOPE: Record<string, string> = {
  PER_PERSON: '每人',
  PER_GROUP: '每单',
  PER_ROOM: '每间',
  PER_NIGHT: '每晚',
  PER_ITEM: '每份',
}

const COST_STATUS: Record<string, string> = {
  KNOWN: '已确认价格',
  ESTIMATED: '估算价格',
  UNKNOWN: '价格未知',
}

const PREP_CATEGORY: Record<string, string> = {
  DOCUMENT: '证件',
  BOOKING: '预订',
  CLOTHING: '衣物',
  EQUIPMENT: '装备',
  HEALTH: '健康',
  REFRESH: '出行前核对',
}

const PREP_PRIORITY: Record<string, string> = { REQUIRED: '必须', RECOMMENDED: '建议', OPTIONAL: '可选' }

const LODGING_TYPE: Record<string, string> = {
  STAR_HOTEL: '星级酒店',
  CHAIN: '连锁酒店',
  LOCAL_FEATURED: '本地特色',
  HOSTEL: '青年旅舍',
  ECONOMY: '经济型',
}

const WALKING_BURDEN: Record<string, string> = { LOW: '步行少', MEDIUM: '步行适中', HIGH: '步行较多' }

const LEG_SOURCE: Record<string, string> = {
  MAP_PROVIDER: '地图服务',
  MANUAL_MATRIX: '人工矩阵',
  FAKE: '模拟数据',
}

const PLAN_VALIDATION: Record<string, string> = {
  PENDING: '待验证',
  VALID: '计划有效',
  INVALID: '计划无效',
}

const DATA_ASSURANCE: Record<string, string> = {
  VERIFIED: '数据已核实',
  DEGRADED: '数据降级',
  MOCK: '模拟数据',
  INSUFFICIENT: '数据不足',
}

const GUIDE_READINESS: Record<string, string> = {
  READY: '可以直接出发',
  READY_WITH_WARNINGS: '可用，但有需要留意的项',
  NOT_READY: '暂不可用',
}

const LIFECYCLE: Record<string, string> = {
  DRAFT: '草稿',
  CONFIRMED: '已确认',
  EXECUTING: '执行中',
  COMPLETED: '已完成',
  OUTDATED: '已过期',
}

const SEVERITY: Record<string, string> = { WARNING: '提醒', ERROR: '冲突' }

const ALTERNATIVE_TRIGGER: Record<string, string> = {
  LATE_START: '起晚/晚出发',
  RAIN: '下雨',
  CLOSED: '临时闭馆',
  FATIGUE: '体力不足',
  BUDGET_CUT: '压缩预算',
  TIME_SHORTAGE: '时间不够',
  CROWDED: '人流过大',
  OTHER: '其他情况',
}

const LODGING_AREA_HINT: Record<string, string> = {
  NEAR_TRANSIT: '近交通',
  CLEAN: '干净',
  QUIET: '安静',
  FAMILY_FRIENDLY: '适合家庭',
  BUDGET: '性价比高',
}

function pick(table: Record<string, string>, value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback
  return table[value] ?? value
}

export const stageLabel = (value?: string | null) => pick(STAGE, value, '—')
export const nodeTypeLabel = (value?: string | null) => pick(NODE_TYPE, value, '行程')
export const intensityLabel = (value?: string | null) => pick(INTENSITY, value)
export const modeLabel = (value?: string | null) => pick(MODE, value)
export const costCategoryLabel = (value?: string | null) => pick(COST_CATEGORY, value)
export const pricingScopeLabel = (value?: string | null) => pick(PRICING_SCOPE, value)
export const costStatusLabel = (value?: string | null) => pick(COST_STATUS, value)
export const prepCategoryLabel = (value?: string | null) => pick(PREP_CATEGORY, value)
export const prepPriorityLabel = (value?: string | null) => pick(PREP_PRIORITY, value)
export const lodgingTypeLabel = (value?: string | null) => pick(LODGING_TYPE, value)
export const walkingBurdenLabel = (value?: string | null) => pick(WALKING_BURDEN, value)
export const legSourceLabel = (value?: string | null) => pick(LEG_SOURCE, value)
export const planValidationLabel = (value?: string | null) => pick(PLAN_VALIDATION, value)
export const dataAssuranceLabel = (value?: string | null) => pick(DATA_ASSURANCE, value)
export const guideReadinessLabel = (value?: string | null) => pick(GUIDE_READINESS, value)
export const lifecycleLabel = (value?: string | null) => pick(LIFECYCLE, value)
export const severityLabel = (value?: string | null) => pick(SEVERITY, value)
export const alternativeTriggerLabel = (value?: string | null) => pick(ALTERNATIVE_TRIGGER, value)
export const qualityFlagLabel = (value?: string | null) => pick(LODGING_AREA_HINT, value)

/** 后端 `details` / `mock_items` 里的资源前缀 → 中文。 */
export function sourceItemLabel(value: string): string {
  const [prefix, id] = value.split(':')
  const table: Record<string, string> = {
    weather: '天气',
    route: '路线',
    lodging: '住宿',
    poi: '景点',
    restaurant: '餐饮',
    intercity: '城际交通',
    fact: '事实记录',
    evidence: '证据',
  }
  const name = table[prefix]
  return name ? `${name}（模拟）` : value
}

/** 后端 `WarningItem` 的 code → 中文标题。消息体本身用后端原文。 */
export function warningTitle(code: string): string {
  const table: Record<string, string> = {
    MOCK_DATA_IN_DEMO: '演示模式使用模拟数据',
    MISSING_PROFILE_FIELDS: '关键信息还不完整',
    OUT_OF_KNOWLEDGE_COVERAGE: '超出知识库覆盖范围',
    DEGRADED_DATA: '部分数据已降级',
    DATA_EXPIRED: '数据已过期',
    LIMITED_EVIDENCE: '证据不足',
  }
  return table[code] ?? code
}
