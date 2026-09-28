/**
 * B3：把后端的"追问清单"变成前端可点的结构化表单。
 *
 * 数据来源是**统一信封里的 warning**，不是新增接口字段——
 * `CONTRACTS.md` §13.1 的 `SendMessageData` 里没有结构化追问字段，
 * 追问项由 `WarningItem{code:"MISSING_PROFILE_FIELDS", details:{字段名: ...}}` 携带
 * （`backend/app/services/reply_builder.py`）。
 *
 * 关于「文案」（Q6 结论，2026-09-27 三人拍板，见 `docs/Q6-Q8-Q9-决策材料.md`）：
 * - `assistant_message` 是**给人看的展示文本，永不被程序解析**，前端不从中拆字段；
 * - 追问文案的权威来源是后端 `details` 的 **value**（Q6 方案 B 已把该结构写进契约，
 *   后端 `build_questions()` 的输出就是它）。下面 `META` 里的 question 是**兜底副本**，
 *   只在后端还没给文案（value 仍等于字段名）时使用；
 * - 所以这里不再自称"与后端保持一致"——历史上那句注释是错的，
 *   5 个字段里曾有 3 个已经漂移，现在改为「后端优先、本地兜底」的取值顺序。
 *
 * 字段名与顺序跟后端 `FINALIZE_REQUIRED_FIELDS` 对齐
 * （`backend/app/schemas/v04/models.py`）。前端**只负责收集**，
 * 不判断"够不够"，也不替后端算 `duration_days`。
 */

import type { WarningItem } from '@/types/contract'

/** 与后端 `FINALIZE_REQUIRED_FIELDS` 同一顺序。 */
export const FIELD_ORDER = ['departure_city', 'start_date', 'end_date', 'traveler_count', 'budget'] as const

export type FieldName = (typeof FIELD_ORDER)[number]

export interface FieldMeta {
  name: string
  label: string
  /**
   * 追问文案的**兜底副本**：后端在 `details` 里给了文案就用后端的（见 `resolveMeta`），
   * 没给才用这里的。不要在这里追求与后端逐字一致，那正是 Q6 要修掉的漂移。
   */
  question: string
  kind: 'text' | 'date' | 'number' | 'budget'
  placeholder?: string
  quickPicks?: string[]
}

/**
 * 本地兜底副本。question 与后端 `services/missing_fields.py:_TEXT` **逐字对齐**
 * （2026-09-28 对齐：此前 5 个字段里有 3 个漂移，正是 Q6 要修的问题）。
 *
 * 改动约定：这里只填"后端还没给文案时"的兜底；后端一旦通过 `details` 下发文案，
 * 展示的就是后端的（见 `resolveMeta`）。真要改文案，优先改后端，别在这里长期维护第二份。
 */
const META: Record<string, FieldMeta> = {
  departure_city: {
    name: 'departure_city',
    label: '出发地',
    question: '你从哪个城市出发？',
    kind: 'text',
    placeholder: '例如：上海',
    quickPicks: ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安'],
  },
  start_date: {
    name: 'start_date',
    label: '出发日期',
    question: '大概哪天出发？（例如：10月2号）',
    kind: 'date',
  },
  end_date: {
    name: 'end_date',
    label: '返回日期',
    question: '哪天回来？（例如：10月6号；也可以直接说玩几天）',
    kind: 'date',
  },
  traveler_count: {
    name: 'traveler_count',
    label: '出行人数',
    question: '几个人一起去？',
    kind: 'number',
    quickPicks: ['1', '2', '3', '4', '5', '6'],
  },
  budget: {
    name: 'budget',
    label: '总预算',
    question: '这趟旅行总预算大概多少？（例如：5000 元）',
    kind: 'budget',
  },
}

/** 未知字段（后端将来加字段时）也能渲染出来，不至于整块追问卡消失。 */
function fallbackMeta(name: string): FieldMeta {
  return { name, label: name, question: `请补充 ${name}`, kind: 'text' }
}

export function fieldMeta(name: string): FieldMeta {
  return META[name] ?? fallbackMeta(name)
}

/**
 * 从信封 `warnings` 取出**后端给的追问文案**（`details` 的 value）。
 *
 * Q6 之前 value 就是字段名本身（`{name: name}`），那种情况不算文案，直接跳过；
 * Q6 方案 B 落地后 value 是 `build_questions()` 的输出，这里就会拿到真正的文案，
 * 追问卡优先用它 —— 文案变成单一来源，前端 `META` 退回兜底位。
 */
export function backendQuestions(warnings: WarningItem[]): Record<string, string> {
  const warning = warnings.find((item) => item.code === 'MISSING_PROFILE_FIELDS')
  const details = warning?.details
  if (!details) return {}
  const result: Record<string, string> = {}
  for (const [name, value] of Object.entries(details)) {
    const text = typeof value === 'string' ? value.trim() : ''
    if (text && text !== name) result[name] = text
  }
  return result
}

/**
 * 解析一个字段的展示信息：**后端文案优先，本地 `META` 兜底**。
 *
 * 顺序不能反：本地副本只是 UI 骨架（label / 输入控件类型 / 快捷选项），
 * 文案一旦有了单一来源就不该再让两套措辞同时出现在同一屏。
 */
export function resolveMeta(name: string, backend: Record<string, string> = {}): FieldMeta {
  const meta = fieldMeta(name)
  const question = backend[name]
  return question ? { ...meta, question } : meta
}

/**
 * 从信封 `warnings` 里取出仍然缺失的字段名（**只看 key**）。
 *
 * value 的语义是「追问文案」，由 `backendQuestions()` 单独取用 —— 两个用途分开，
 * 免得有人顺手拿 value 当字段名（Q6 之前那个形态下会"刚好对"，之后就会错）。
 */
export function extractMissingFields(warnings: WarningItem[]): string[] {
  const warning = warnings.find((item) => item.code === 'MISSING_PROFILE_FIELDS')
  if (!warning?.details) return []
  const names = Object.keys(warning.details)
  // 按后端顺序排；未收录的名字排在后面
  return names.sort((a, b) => {
    const ia = FIELD_ORDER.indexOf(a as FieldName)
    const ib = FIELD_ORDER.indexOf(b as FieldName)
    return (ia === -1 ? Number.MAX_SAFE_INTEGER : ia) - (ib === -1 ? Number.MAX_SAFE_INTEGER : ib)
  })
}

// --- 预算档位 ----------------------------------------------------------------

export interface BudgetTier {
  amount: number
  hint: string
}

/**
 * 预算档位（B3 的方案：让用户点选，不必手打数字）。
 *
 * 用户拍板的方案是"500-50000 每 5000 间隔"，落到界面上取 5000–50000 每 5000 一档，
 * 另给 1000/3000 两个短途低档；再高的额度走精确输入，避免档位长到点不过来。
 * 选择的档位**原值当作 `Money(amount=...)` 报给后端**，不在这里做任何"打包价"换算。
 */
export const BUDGET_TIERS: BudgetTier[] = [
  { amount: 5000, hint: '3-4 天 · 常规' },
  { amount: 10000, hint: '5 天 · 常规' },
  { amount: 15000, hint: '5-6 天 · 舒适' },
  { amount: 20000, hint: '6-7 天 · 舒适' },
  { amount: 25000, hint: '7 天 · 品质' },
  { amount: 30000, hint: '7-8 天 · 品质' },
  { amount: 35000, hint: '长线 · 品质' },
  { amount: 40000, hint: '长线 · 高端' },
  { amount: 45000, hint: '长线 · 高端' },
  { amount: 50000, hint: '长线 · 高端' },
]

/** 短途低档，单独一行。 */
export const BUDGET_LOW_TIERS: BudgetTier[] = [
  { amount: 1000, hint: '周边 1-2 天' },
  { amount: 3000, hint: '短途 2-3 天' },
]

/** 预算弹性的两档口径，直接对应契约的 `budget_flexibility`（FIXED / NEGOTIABLE）。 */
export type BudgetFlexibility = 'FIXED' | 'NEGOTIABLE'

/** 表单里"当前填了什么"。所有字段可选，用户想答几项答几项。 */
export interface ClarificationForm {
  text: Partial<Record<string, string>>
  traveler_count: number | null
  budget: number | null
  budgetFlexible: BudgetFlexibility
  /** 用户只说"玩几天"时的补充，追加到消息末尾由后端解析 */
  days: number | null
}

export function emptyForm(): ClarificationForm {
  return { text: {}, traveler_count: null, budget: null, budgetFlexible: 'NEGOTIABLE', days: null }
}

/** 表单是否一个字都没填（用来禁用提交按钮）。 */
export function isFormEmpty(form: ClarificationForm): boolean {
  if (form.traveler_count !== null) return false
  if (form.budget !== null) return false
  if (form.days !== null) return false
  return Object.values(form.text).every((value) => !value || !value.trim())
}

/**
 * 表单 → 一句自然语言，交给后端现有的解析链路。
 *
 * 为什么不直接 POST 结构化字段：`SendMessageRequest` 只收 `text`
 * （`CONTRACTS.md` §13.1），结构化补充没有对应接口。而且"人话"进、
 * 后端照常走 LLM/规则解析，才跟前端自由输入是同一条路径，不会出现两套行为。
 */
export function buildClarificationMessage(form: ClarificationForm): string {
  const parts: string[] = []

  const text = (name: string) => form.text[name]?.trim() ?? ''

  if (text('departure_city')) parts.push(`出发地：${text('departure_city')}`)
  if (text('start_date')) parts.push(`出发日期：${text('start_date')}`)
  if (text('end_date')) parts.push(`返回日期：${text('end_date')}`)
  if (form.days !== null && form.days > 0) parts.push(`共玩 ${form.days} 天`)
  if (form.traveler_count !== null) parts.push(`人数：${form.traveler_count} 人`)
  if (form.budget !== null) {
    // "不能超"是后端规则解析器 `_FIXED_BUDGET_WORDS` 认的关键词，
    // 文案必须和它对齐，否则 FIXED 意图会被解析成 NEGOTIABLE
    parts.push(
      form.budgetFlexible === 'NEGOTIABLE'
        ? `总预算：${form.budget} 元，可以上下浮动一些`
        : `总预算：${form.budget} 元，不能超`,
    )
  }

  // 后端将来新增的字段，原样带过去
  for (const [name, value] of Object.entries(form.text)) {
    if (FIELD_ORDER.includes(name as FieldName)) continue
    if (value && value.trim()) parts.push(`${fieldMeta(name).label}：${value.trim()}`)
  }

  return parts.join('；')
}
