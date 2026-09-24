/**
 * B3：把后端的"追问清单"变成前端可点的结构化表单。
 *
 * 数据来源是**统一信封里的 warning**，不是新增接口字段——
 * `CONTRACTS.md` §13.1 的 `SendMessageData` 里没有结构化追问字段，
 * 追问项由 `WarningItem{code:"MISSING_PROFILE_FIELDS", details:{字段名: 字段名}}` 携带
 * （`backend/app/services/reply_builder.py`）。
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
  /** 与后端 `build_questions()` 的追问文案保持一致，用户看到的问题两端口径统一 */
  question: string
  kind: 'text' | 'date' | 'number' | 'budget'
  placeholder?: string
  quickPicks?: string[]
}

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
    question: '大概哪天出发？',
    kind: 'date',
  },
  end_date: {
    name: 'end_date',
    label: '返回日期',
    question: '哪天回来？',
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
    question: '这趟旅行总预算大概多少？',
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
 * 从信封 `warnings` 里取出仍然缺失的字段。
 *
 * 注意：`details` 的 value 后端填的是字段名本身（`{name: name}`），
 * 所以这里**只看 key**，不要依赖 value 的语义。
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
