/**
 * 会话编排 Store（B 线的前端状态中枢）。
 *
 * 它是**唯一**知道"后端现在到哪一步"的地方，组件只读它、不各自发请求。
 * 三条必须守住的规矩：
 *
 * 1. 每个响应的 `warnings` 都要留住并展示——模拟数据、缺失字段、覆盖不足
 *    都是正常工作流状态，不能悄悄吞掉（`CONTRACTS.md` §13.2）。
 * 2. `ok=false` 不是"页面崩了"，而是把 `error.code` 翻成中文给用户看，
 *    会话本身继续可用（例如 VERSION_CONFLICT 只需刷新一次）。
 * 3. 攻略（`TravelGuide`）的正文目前**只能来自官方 fixture**：
 *    `/api/guides/...` 属于 C7，尚未实现。`guideOrigin` 明确标注来源，
 *    绝不让演示数据冒充后端产物。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError } from '@/api/client'
import { createSession, getSession, sendMessage } from '@/api/sessions'
import type {
  ChatMessage,
  Conflict,
  DestinationRecommendation,
  PlanState,
  RunMode,
  TripProfile,
  TravelGuide,
  WarningItem,
} from '@/types/contract'
import { extractMissingFields, FIELD_ORDER } from '@/utils/clarification'
import { fixtureEnabled, loadFixtureDraft, loadFixtureGuide } from '@/utils/fixtureLoader'

export type GuideOrigin = 'api' | 'fixture' | 'none'

function nowLabel(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(now.getHours())}:${pad(now.getMinutes())}`
}

// --- 会话持久化 ---------------------------------------------------------------
//
// 为什么必须做：后端会话是有状态的（画像版本、Draft、候选都在服务端），
// 用户刷新页面后如果重新 createSession，等于把正在进行的对话扔掉重开。
// localStorage 只存"找得回会话的钥匙"，**不复制后端状态**——
// 恢复时用 GET /api/sessions/{id} 重新拉权威状态，前端不自己拼装。

const STORAGE_KEY = 'travelsense.session.v1'

interface PersistedSession {
  sessionId: string
  runMode: RunMode
  messages: ChatMessage[]
  profileVersion: number | null
}

function readSavedSession(): PersistedSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedSession
    return parsed?.sessionId && Array.isArray(parsed.messages) ? parsed : null
  } catch {
    // 存的是坏数据就当没有，不能因为它挡住新会话
    return null
  }
}

function writeSavedSession(session: PersistedSession | null): void {
  try {
    if (!session) {
      localStorage.removeItem(STORAGE_KEY)
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    }
  } catch {
    // 隐私模式 / 配额满：持久化失败不影响当次会话
  }
}

export const useSessionStore = defineStore('session', () => {
  // --- 原始响应状态 ---------------------------------------------------------
  const runMode = ref<RunMode>('DEMO')
  const sessionId = ref<string | null>(null)
  const planState = ref<PlanState | null>(null)
  const stage = ref<string>('CREATED')
  const tripProfile = ref<TripProfile | null>(null)
  const destinationCandidates = ref<DestinationRecommendation[]>([])
  const conflicts = ref<Conflict[]>([])
  const warnings = ref<WarningItem[]>([])
  const degradedItems = ref<string[]>([])
  const traceId = ref<string | null>(null)

  // --- 界面状态 -------------------------------------------------------------
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const error = ref<{ code: string; message: string } | null>(null)
  const guide = ref<TravelGuide | null>(null)
  const guideOrigin = ref<GuideOrigin>('none')
  const guideNotice = ref<string | null>(null)
  /** 演示通道的说明（本地造出来的界面状态，必须显式告知，不能冒充后端行为） */
  const demoNotice = ref<string | null>(null)
  /** 用户已手动关闭的提示。同一会话内不再打扰；内容变化时视为新提示。 */
  const dismissedKeys = ref<Set<string>>(new Set())

  // --- 派生 -----------------------------------------------------------------
  const missingFields = computed<string[]>(() => {
    const fromWarning = extractMissingFields(warnings.value)
    if (fromWarning.length > 0) return fromWarning
    // 追问阶段但没带 warning（理论上不该出现）：按契约必填字段全列，让用户一次性补齐
    return stage.value === 'ASKING_CLARIFICATION' ? [...FIELD_ORDER] : []
  })

  const needsClarification = computed(
    () => stage.value === 'ASKING_CLARIFICATION' || missingFields.value.length > 0,
  )
  const hasSession = computed(() => Boolean(sessionId.value))
  const mockInUse = computed(
    () =>
      runMode.value === 'DEMO' ||
      warnings.value.some((item) => item.code === 'MOCK_DATA_IN_DEMO') ||
      (guide.value?.sources_and_freshness.mock_items.length ?? 0) > 0,
  )

  // --- 提示的关闭（用户点一次 × 就不再打扰） ---------------------------------
  //
  // 注意不能简单地"关闭 = 删掉 warnings"：warnings 每轮响应都会重新灌进来，
  // 删了下一轮又回来。正确做法是记录"已关闭的提示"，显示时过滤。
  // Key 含 details 的字段名集合——缺失字段补齐后（集合变化）视为新提示，会重新出现。

  function warningKeyOf(item: WarningItem): string {
    const detailKeys = Object.keys(item.details ?? {}).sort().join(',')
    return `${item.code}|${detailKeys}`
  }

  const degradedKey = computed(() => `DEGRADED|${[...degradedItems.value].sort().join(',')}`)

  const visibleWarnings = computed(() =>
    warnings.value.filter((item) => !dismissedKeys.value.has(warningKeyOf(item))),
  )
  const visibleDegradedItems = computed(() =>
    dismissedKeys.value.has(degradedKey.value) ? [] : degradedItems.value,
  )

  function dismissWarning(item: WarningItem): void {
    dismissedKeys.value.add(warningKeyOf(item))
  }

  function dismissDegraded(): void {
    dismissedKeys.value.add(degradedKey.value)
  }

  function dismissGuideNotice(): void {
    guideNotice.value = null
  }

  function pushMessage(role: ChatMessage['role'], text: string, atStage?: string): void {
    if (!text?.trim()) return
    messages.value.push({ role, text, stage: atStage, at: nowLabel() })
  }

  /** 只在真实会话下落盘；演示通道不持久化，避免误导下次打开。 */
  function persist(): void {
    if (!sessionId.value) {
      writeSavedSession(null)
      return
    }
    writeSavedSession({
      sessionId: sessionId.value,
      runMode: runMode.value,
      messages: messages.value,
      profileVersion: tripProfile.value?.profile_version ?? null,
    })
  }

  function absorbWarnings(items: WarningItem[] | undefined): void {
    warnings.value = items ?? []
  }

  function describeError(cause: unknown): { code: string; message: string } {
    if (cause instanceof ApiError) {
      return { code: cause.code, message: cause.message }
    }
    return { code: 'UNKNOWN', message: cause instanceof Error ? cause.message : '未知错误' }
  }

  /**
   * 创建会话；同模式下有已保存的会话则先尝试恢复。
   * 后端是内存存储，服务重启后旧会话会 404——那种情况静默降级为新建，不打扰用户。
   */
  async function init(mode: RunMode = 'DEMO'): Promise<void> {
    runMode.value = mode
    loading.value = true
    error.value = null

    const saved = readSavedSession()
    if (saved && saved.runMode === mode) {
      try {
        const result = await getSession(saved.sessionId)
        sessionId.value = saved.sessionId
        planState.value = result.data
        stage.value = result.data.stage
        messages.value = saved.messages
        traceId.value = result.traceId
        absorbWarnings(result.warnings)
        loading.value = false
        await refreshState()
        return
      } catch {
        writeSavedSession(null)
      }
    }

    try {
      const result = await createSession(mode)
      sessionId.value = result.data.session_id
      planState.value = result.data.state
      stage.value = result.data.state.stage
      traceId.value = result.traceId
      absorbWarnings(result.warnings)
      pushMessage('assistant', '你好，我是识途。告诉我你想去哪、从哪出发、什么时候走、几个人、大概预算，我来帮你把行程定下来。')
      persist()
    } catch (cause) {
      error.value = describeError(cause)
    } finally {
      loading.value = false
    }
  }

  /** 发送一轮自然语言，把后端返回的画像/候选/冲突/警告全部吸收。 */
  async function send(text: string): Promise<void> {
    const content = text.trim()
    if (!content || loading.value) return
    if (!sessionId.value) {
      await init(runMode.value)
      if (!sessionId.value) return
    }

    pushMessage('user', content)
    loading.value = true
    error.value = null

    try {
      const result = await sendMessage(sessionId.value, content, tripProfile.value?.profile_version ?? null)
      const data = result.data

      stage.value = data.stage
      warnings.value = result.warnings ?? []
      traceId.value = result.traceId
      if (data.trip_profile) tripProfile.value = data.trip_profile
      destinationCandidates.value = data.destination_candidates ?? []
      conflicts.value = data.conflicts ?? []
      degradedItems.value = data.degraded_items ?? []
      pushMessage('assistant', data.assistant_message, data.stage)

      // 后端只给了 guide_id，正文要等 C7 的攻略接口
      if (data.guide_id) {
        stage.value = 'READY'
      }
      await syncGuide(data.guide_id)
      await refreshState()
      persist()
    } catch (cause) {
      const described = describeError(cause)
      error.value = described
      pushMessage('assistant', `这一轮没走通：${described.message}`)
      if (described.code === 'VERSION_CONFLICT') {
        // 版本冲突只需要重新拉一次状态，用户不用重新输
        await refreshState()
      }
    } finally {
      loading.value = false
    }
  }

  async function refreshState(): Promise<void> {
    if (!sessionId.value) return
    try {
      const result = await getSession(sessionId.value)
      planState.value = result.data
      stage.value = result.data.stage
      absorbWarnings(result.warnings)
    } catch {
      // 状态刷新失败不影响已显示的对话内容，静默即可
    }
  }

  /**
   * 攻略正文装配。
   *
   * 后端攻略接口（C7）就绪前，只能在演示模式下读官方 fixture，
   * 并在界面上**显式标注**这是示例数据。
   */
  async function syncGuide(guideId: string | null): Promise<void> {
    if (!guideId) {
      guide.value = null
      guideOrigin.value = 'none'
      guideNotice.value = null
      return
    }
    // TODO(C7)：改为 GET /api/guides/{guide_id} 后直接使用接口返回的 TravelGuide
    const fixture = loadFixtureGuide()
    if (fixture) {
      guide.value = fixture
      guideOrigin.value = 'fixture'
      guideNotice.value =
        '后端攻略接口（C7）尚未实现，本页展示的是仓库官方 fixture（fixtures/valid/travel_guide.json），仅用于验证七部分组装与展示，不是本次会话的真实产物。'
    } else {
      guide.value = null
      guideOrigin.value = 'none'
      guideNotice.value = `后端已生成攻略 ${guideId}，但攻略接口尚未实现，暂时无法取回正文。`
    }
  }

  /** 演示通道：不连后端，直接看七部分组装效果。 */
  async function loadFixtureDemo(): Promise<void> {
    const fixture = loadFixtureGuide()
    if (!fixture) {
      error.value = { code: 'CONTRACT_MISMATCH', message: '未启用 fixture 演示（VITE_ENABLE_FIXTURE_DEMO=false）' }
      return
    }
    guide.value = fixture
    guideOrigin.value = 'fixture'
    stage.value = 'READY'
    runMode.value = fixture.run_mode
    guideNotice.value =
      '演示模式：数据来自仓库官方 fixture（fixtures/valid/travel_guide.json），不经过后端，也不能用来证明规划链路的正确性。'
    demoNotice.value = null
    pushMessage('assistant', '已载入官方示例攻略，可以直接查看右侧七个部分。', 'READY')
    persist()
  }

  /**
   * 演示通道：把 B3 的追问卡单独亮出来。
   *
   * 缺哪两个字段来自官方 draft 样例（`trip_profile_draft_incomplete.json`
   * 的 `missing_fields = ["end_date","budget"]`），warning 的 code 与 details
   * 形状与后端 `reply_builder._build_warnings()` 完全一致——
   * 这样才能验证"前端确实只按 warning 渲染"，而不是前端自己判断缺什么。
   */
  async function loadFixtureClarificationDemo(): Promise<void> {
    const draft = loadFixtureDraft()
    const missing = draft?.missing_fields ?? ['end_date', 'budget']
    stage.value = 'ASKING_CLARIFICATION'
    guide.value = null
    guideOrigin.value = 'none'
    guideNotice.value = null
    warnings.value = [
      {
        code: 'MISSING_PROFILE_FIELDS',
        message: '关键信息还不完整，请按追问补充。',
        details: Object.fromEntries(missing.map((name) => [name, name])),
      },
    ]
    demoNotice.value =
      '这是本地的追问卡预览：warning 的 code 与 details 形状与后端一致，但整条状态是前端造出来的，不经过后端。真实追问由后端解析用户输入后判定。'
    messages.value = []
    pushMessage(
      'user',
      '国庆想去个有好吃的地方，从上海出发，两个人',
      'PARSING_REQUEST',
    )
    pushMessage(
      'assistant',
      '为了给你推荐合适的目的地，还需要确认几件事：哪天回来？这趟旅行总预算大概多少？',
      'ASKING_CLARIFICATION',
    )
    persist()
  }

  function dismissDemoNotice(): void {
    demoNotice.value = null
  }

  function dismissError(): void {
    error.value = null
  }

  function reset(): void {
    sessionId.value = null
    planState.value = null
    stage.value = 'CREATED'
    tripProfile.value = null
    destinationCandidates.value = []
    conflicts.value = []
    warnings.value = []
    degradedItems.value = []
    traceId.value = null
    messages.value = []
    error.value = null
    guide.value = null
    guideOrigin.value = 'none'
    guideNotice.value = null
    demoNotice.value = null
    dismissedKeys.value = new Set()
    persist()
  }

  return {
    // state
    runMode,
    sessionId,
    planState,
    stage,
    tripProfile,
    destinationCandidates,
    conflicts,
    warnings,
    degradedItems,
    traceId,
    messages,
    loading,
    error,
    guide,
    guideOrigin,
    guideNotice,
    demoNotice,
    visibleWarnings,
    visibleDegradedItems,
    warningKeyOf,
    fixtureEnabled,
    // derived
    missingFields,
    needsClarification,
    hasSession,
    mockInUse,
    // actions
    init,
    send,
    refreshState,
    loadFixtureDemo,
    loadFixtureClarificationDemo,
    dismissDemoNotice,
    dismissGuideNotice,
    dismissWarning,
    dismissDegraded,
    dismissError,
    reset,
  }
})
