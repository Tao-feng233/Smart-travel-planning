/**
 * 展示格式化工具。
 *
 * 两条规矩（`handoff/B_交接说明.md`）：
 * 1. **只做展示**，不改动数值语义；金额一律从契约的 `Money` 对象读，不在前端复算预算。
 * 2. 时间戳带 `+08:00` 时区，**不要用 `new Date()` 转本地**——会被 UTC 平移。
 *    这里一律按字符串切片读，避免"10月2日 09:00 显示成 10月2日 01:00"。
 */

import type { Money } from '@/types/contract'

/** 千分位；整数不带小数点。 */
function number(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString('zh-CN')
    : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function currencySign(currency: string): string {
  return currency === 'CNY' ? '\u00a5' : `${currency} `
}

/**
 * `Money` → 展示文案。契约保证 `amount` 与 `min/max` 互斥且必有一方，
 * 但前端仍然容错，避免后端契约漂移时整页崩掉。
 */
export function formatMoney(money: Money | null | undefined): string {
  if (!money) return '费用未知'
  const sign = currencySign(money.currency ?? 'CNY')

  if (money.amount !== null && money.amount !== undefined) {
    return `${sign}${number(money.amount)}`
  }
  const { min_amount: min, max_amount: max } = money
  if (min !== null && min !== undefined && max !== null && max !== undefined) {
    return min === max ? `${sign}${number(min)}` : `${sign}${number(min)}~${number(max)}`
  }
  if (min !== null && min !== undefined) return `${sign}${number(min)} 起`
  if (max !== null && max !== undefined) return `${sign}${number(max)} 以内`
  return '费用未知'
}

/** 该金额是否只是区间/未知（用于决定要不要加"估算"标签）。 */
export function isEstimate(money: Money | null | undefined): boolean {
  if (!money) return true
  return money.amount === null || money.amount === undefined
}

/** `2026-10-02` → `10月2日` */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parts = value.slice(0, 10).split('-')
  if (parts.length !== 3) return value
  return `${Number(parts[1])}月${Number(parts[2])}日`
}

/** `2026-10-02` → `2026-10-02（周五）` */
export function formatDateWithWeekday(value: string | null | undefined): string {
  if (!value) return '—'
  const day = value.slice(0, 10)
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const index = new Date(`${day}T00:00:00Z`).getUTCDay()
  return `${day}（${weekday[index]}）`
}

/** `2026-10-03T09:00:00+08:00` → `09:00` */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const match = /T(\d{2}):(\d{2})/.exec(value)
  return match ? `${match[1]}:${match[2]}` : '—'
}

/** `2026-10-03T09:00:00+08:00` → `10月3日 09:00` */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return `${formatDate(value)} ${formatTime(value)}`
}

/** `2026-10-03T09:00:00+08:00` → `10月3日 09:00-11:00`；跨日则补出到日期 */
export function formatTimeRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return '—'
  const sameDay = start.slice(0, 10) === end.slice(0, 10)
  return sameDay
    ? `${formatDate(start)} ${formatTime(start)}-${formatTime(end)}`
    : `${formatDateTime(start)} → ${formatDateTime(end)}`
}

/** `2026-10-02` ~ `2026-10-05` → `10月2日 - 10月5日` */
export function formatDateRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return '—'
  if (start === end) return formatDate(start)
  return `${formatDate(start)} - ${formatDate(end)}`
}

/** 分钟 → `1小时30分` / `45分钟` */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '—'
  if (minutes < 60) return `${minutes}分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours}小时` : `${hours}小时${rest}分`
}

/** 天数文案：`4 天 3 晚` */
export function formatDuration(days: number | null | undefined): string {
  if (!days) return '—'
  return days > 1 ? `${days} 天 ${days - 1} 晚` : '1 天'
}

/** 列表为空时的统一占位。 */
export function orDash(values: readonly string[] | null | undefined): string {
  return values && values.length > 0 ? values.join('、') : '—'
}

/** `2026-09-24T18:00:00+08:00` → `2026-09-24 18:00` */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  return `${value.slice(0, 10)} ${formatTime(value)}`
}

/** 出行人构成 → `2 成人` / `2 成人 1 儿童` */
export function formatComposition(
  composition: { adults: number; children: number; seniors: number } | null | undefined,
): string {
  if (!composition) return '—'
  const parts: string[] = []
  if (composition.adults) parts.push(`${composition.adults} 成人`)
  if (composition.children) parts.push(`${composition.children} 儿童`)
  if (composition.seniors) parts.push(`${composition.seniors} 老人`)
  return parts.length > 0 ? parts.join(' ') : '—'
}
