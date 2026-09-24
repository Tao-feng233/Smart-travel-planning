/**
 * 契约样例（fixtures）加载器 —— **只在后端攻略接口就绪前用于演示**。
 *
 * 背景：`/api/guides/...` 属于 C7，尚未实现。所以本轮 B 线能拿到的只有
 * `guide_id`，拿不到 `TravelGuide` 正文。为了先把 B6 的七部分组装**看得见**，
 * 演示模式下直接读仓库根目录的官方 fixture
 * （`fixtures/valid/travel_guide.json` 等），**不复制、不修改、不新增模拟数据**。
 *
 * 一旦 C7 的攻略接口可用，`GuideView` 会自动切到接口数据（见 `stores/session.ts`），
 * 这条演示通道由 `VITE_ENABLE_FIXTURE_DEMO` 控制，默认可以在 .env 里关掉。
 */

import type { TravelGuide, TripProfile } from '@/types/contract'

/** fixture 文件统一是 `{ "model": "...", "data": {...} }` 信封。 */
interface FixtureFile<T> {
  model: string
  data: T
}

export interface DraftFixture {
  session_id: string
  profile_version: number
  departure_city: string | null
  start_date: string | null
  end_date: string | null
  traveler_count: number | null
  budget: unknown
  missing_fields: string[]
}

// 相对路径从 src/utils/ 上溯到仓库根：utils → src → frontend → 仓库根
const guideModule = import.meta.glob<FixtureFile<TravelGuide>>('../../../fixtures/valid/travel_guide.json', {
  eager: true,
})
const profileModule = import.meta.glob<FixtureFile<TripProfile>>('../../../fixtures/valid/trip_profile.json', {
  eager: true,
})
const draftModule = import.meta.glob<FixtureFile<DraftFixture>>(
  '../../../fixtures/valid/trip_profile_draft_incomplete.json',
  { eager: true },
)

function unwrap<T>(module: Record<string, FixtureFile<T>>): T | null {
  const first = Object.values(module)[0]
  return first?.data ?? null
}

export const fixtureEnabled = import.meta.env.VITE_ENABLE_FIXTURE_DEMO !== 'false'

/** 官方示例攻略（DEMO 模式，`guide_readiness = READY_WITH_WARNINGS`）。 */
export function loadFixtureGuide(): TravelGuide | null {
  if (!fixtureEnabled) return null
  return unwrap<TravelGuide>(guideModule)
}

/** 官方示例画像。 */
export function loadFixtureProfile(): TripProfile | null {
  if (!fixtureEnabled) return null
  return unwrap<TripProfile>(profileModule)
}

/** 官方"信息不全的草稿"样例，用于演示追问卡。 */
export function loadFixtureDraft(): DraftFixture | null {
  if (!fixtureEnabled) return null
  return unwrap<DraftFixture>(draftModule)
}
