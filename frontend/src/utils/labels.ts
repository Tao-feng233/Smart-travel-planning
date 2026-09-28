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
  REPLANNING: '正在按突发重排行程',
  // 计划验证通过、但攻略组装缺素材（`graph/stages.py` GUIDE_INCOMPLETE）。
  // 这里必须与 READY 明确区分：它是「停住了」，不是「好了」。
  GUIDE_INCOMPLETE: '计划已通过，但攻略素材不足',
  READY: '攻略已就绪',
}

/**
 * 真实模式下「链路停在这里、等你处理」的阶段话术。
 *
 * 这三个阶段都**不是过渡态，而是停住了**，所以真实模式下不能沿用状态机的进行时口径：
 * - `REPAIRING`：后端没有可自动执行的修法（实测 `repair_options` 为空），
 *   在等用户决定怎么改。这时说「正在修复冲突」是错的——没有任何东西在跑，
 *   用户会以为再等等就好，实际是**永远等不到**。
 * - `GUIDE_INCOMPLETE`：计划通过验证了，但攻略素材不够，后端刻意不报 READY。
 * - `INSUFFICIENT_DATA`：知识库根本没有覆盖。
 *
 * 演示模式仍显示 `阶段：<原始口径>`，那是给对照后端状态机用的，不变。
 */
const STAGE_STALLED: Record<string, string> = {
  REPAIRING: '有几项要你先确认',
  GUIDE_INCOMPLETE: '攻略素材不足',
  INSUFFICIENT_DATA: '这里暂时查不到资料',
}

/** 真实模式下的停滞态话术；其它阶段返回 `null`（此时不展示阶段标签）。 */
export function stageStalledText(stage?: string | null): string | null {
  if (!stage) return null
  return STAGE_STALLED[stage] ?? null
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

/* 严重度说成人话：写「冲突」的话，跟外面的标题「需要你处理的冲突」叠在一起
   会读成「冲突｜影响整份行程」，等于没说。这里改成用户要做的动作。 */
const SEVERITY: Record<string, string> = { WARNING: '可留意', ERROR: '必须处理' }

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

//: 处理中给用户看的进度话术（比状态机标签更像"我们正在为你做什么"）。
//: 真实模式下状态机标签已收起，等待期间就靠这句让用户知道没卡住。
const STAGE_PROGRESS: Record<string, string> = {
  PARSING_REQUEST: '正在理解你的需求…',
  CHECKING_FIELDS: '正在核对信息…',
  RETRIEVING_DESTINATIONS: '正在检索目的地…',
  RECOMMENDING_DESTINATIONS: '正在挑选合适的目的地…',
  FETCHING_RESOURCES: '正在获取可选资源…',
  FILTERING_RESOURCES: '正在核对可用性…',
  PLANNING: '正在编排每日行程…',
  VALIDATING: '正在校验行程是否走得通…',
  REPAIRING: '正在调整冲突…',
  REPLANNING: '正在按突发重排行程…',
}

/** 处理中的进度话术；认不出的阶段一律退到中性文案，不显示内部枚举名。 */
export function stageProgress(stage?: string | null): string {
  if (!stage) return '正在处理…'
  return STAGE_PROGRESS[stage] ?? '正在处理…'
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
    // 用户点名的某个目的地不在知识库里（C 侧 `reply_builder` 发的，
    // 数据来自 B2 的 `ParseOutcome.dropped_destinations`）。
    // 和上面那条的区别：这条说的是「你说的那个地方暂时去不了」，
    // 上面那条说的是「整个需求都超出覆盖」。
    DESTINATION_OUT_OF_COVERAGE: '有目的地暂时规划不了',
    DEGRADED_DATA: '部分数据已降级',
    DATA_EXPIRED: '数据已过期',
    LIMITED_EVIDENCE: '证据不足',
    // C7 改攻略/报突发成功后附带的改动说明（`routes._guide_change`）。
    CHANGE_NOTE: '本轮改动说明',
  }
  return table[code] ?? code
}
