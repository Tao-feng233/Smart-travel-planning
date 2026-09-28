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
import { confirmGuide, getGuide, reportIncident } from '@/api/guides'
import { createSession, getSession, sendMessage } from '@/api/sessions'
import type {
  ChatMessage,
  Conflict,
  DestinationRecommendation,
  PlanState,
  RunMode,
  TripProfile,
  TravelGuide,
  UserAction,
  VersionLineage,
  WarningItem,
} from '@/types/contract'
import { extractMissingFields, FIELD_ORDER } from '@/utils/clarification'
import { fixtureEnabled, loadFixtureDraft, loadFixtureGuide } from '@/utils/fixtureLoader'
import { stageLabel } from '@/utils/labels'

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
// localStorage 只存"找得回后端状态的钥匙"，**不复制后端状态**——
// 恢复时用 GET /api/sessions/{id} 重新拉权威状态，前端不自己拼装。
//
// 关于攻略 ID：**不用**单独存。`GET /api/sessions/{id}` 返回的 `PlanState`（§10.2）里
// 本来就有 `current_guide_id`，拿着它就能取 `GET /api/guides/{id}` 的权威正文。
//
// 早期这里多存了一个 `guideId` 字段，是因为当时**找错了字段名**：去找 `guide_id`，
// 而契约 §13.1 给这个接口的响应是 `PlanState`，字段名是 `current_guide_id`，
// **压根没有 `guide_id`**（`guide_id` 只出现在 `POST .../messages` 的 `SendMessageData` 里）。
// 名字对不上，就以为接口没给——于是绕道本地存了一把。现在删掉这层绕行。

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
  /** 上一次改攻略/报突发的版本谱系（哪些节点被保留、替换、移除）。 */
  const versionLineage = ref<VersionLineage | null>(null)
  /**
   * 产出上面那份谱系的**改动前**那一版攻略。
   *
   * 为什么留着：谱系里的 `removed_node_ids` 与 `replacement_relations.old_node_id`
   * 是**旧版**节点 ID，在新版正文里查不到，要摊开给用户看就得回到旧版正文查名字。
   * 而"改动前那一版"当次操作就在页面上握着，直接留作索引即可，**不用再请求一次**。
   *
   * （历史版本本身现在可以从后端取回来了：C 已把 `guide_service.store_guide`
   * 改成按 `(guide_id, guide_version)` 保留全部版本，`?version=N` 返回 200，
   * 不再是死参数。这里不用它只是为了省一次请求，不是因为取不到。）
   */
  const lineageBaseGuide = ref<TravelGuide | null>(null)
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
    warnings.value.filter(
      (item) =>
        // 「正在使用模拟数据」是持续状态，已由状态条上的常驻标签传达（且不可关闭）。
        // 这里过滤掉同义的 warning，避免同一件事在顶栏说两遍；用户仍能从标签看到当前数据来源。
        item.code !== 'MOCK_DATA_IN_DEMO' &&
        !dismissedKeys.value.has(warningKeyOf(item)),
    ),
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
    // 「攻略缺什么」的还原通道。
    //
    // `GET /api/sessions/{id}` 按 §13.1 只返回 `PlanState`，里面**没有** `degraded_items`
    // （那个字段只属于 `SendMessageData`），所以刷新页面后缺项清单本来会整条丢失。
    // C 的处理（2026-09-27）：不新增契约字段，改由信封 `warnings` 回带，
    // `code = GUIDE_MATERIAL_MISSING`、`message` 就是缺项文案。
    //
    // 只在**确实带了该 warning** 时才覆盖：`send()` 里 `refreshState()` 紧跟其后跑，
    // 若无条件覆盖，会把 `POST` 刚给的那份 `data.degraded_items` 冲成空。
    const guideMissing = (items ?? [])
      .filter((item) => item.code === 'GUIDE_MATERIAL_MISSING')
      .map((item) => item.message)
    if (guideMissing.length > 0) degradedItems.value = guideMissing
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
        // 权威状态刚刚已经拿到，不必再 refreshState() 打一遍同一个接口。
        // 攻略正文的钥匙就在 state 里（`current_guide_id`），直接用它。
        await syncGuide(result.data.current_guide_id)
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

      // 注意：`guide_id` 不能反过来决定 `stage`。
      // 实测（`backend/app/services/reply_builder.py:121-133`）：当 stage 是
      // `REPAIRING`/`INSUFFICIENT_DATA` 时，响应里带的仍是**持久化的上一版**
      // `current_guide_id`。早先这里有一句 `if (data.guide_id) stage = 'READY'`，
      // 会把"正在修复冲突"改写成"攻略已就绪"，等于前端替后端下结论。
      // 现在 stage 只由后端给，前端不猜。
      await syncGuide(data.guide_id)
      if (data.guide_id && data.stage !== 'READY') {
        guideNotice.value =
          `后端当前阶段是「${stageLabel(data.stage)}」，下面这份是已有的上一版攻略，不是本轮新产出的。`
      }
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
   * C7 就绪后走 `GET /api/guides/{id}`，`guideOrigin = 'api'` 表示正文来自后端。
   * fixture 只留给「演示通道」（`loadFixtureDemo`），不再冒充真实产物。
   */
  async function syncGuide(guideId: string | null): Promise<void> {
    if (!guideId) {
      guide.value = null
      guideOrigin.value = 'none'
      guideNotice.value = null
      versionLineage.value = null
      lineageBaseGuide.value = null
      return
    }
    try {
      const result = await getGuide(guideId)
      guide.value = result.data.travel_guide
      guideOrigin.value = 'api'
      guideNotice.value = null
      // 重新取回的是一份全新的正文，上一次改动的谱系已无上下文，不能留在页面上。
      versionLineage.value = null
      lineageBaseGuide.value = null
      absorbWarnings(result.warnings)
    } catch (cause) {
      // 取不回来时**不清空页面**：保留上一份可见的攻略，把后端给的原因如实标出来。
      // 缺素材时 `error.details` 会写明缺什么（例如 LODGING_CANDIDATES），
      // 用户据此去找数据方补，比一个空白页有用。
      const described = describeError(cause)
      guideNotice.value = `没能取回攻略 ${guideId}：${described.message}`
      if (!guide.value) {
        guideOrigin.value = 'none'
      }
    }
  }

  /**
   * 确认当前攻略（`POST /api/guides/{id}/confirm`）。
   *
   * 后端语义（实测 `app/services/session_service.py:210-240`）：
   * - `lifecycle_status` 置为 `CONFIRMED`、`guide_version` +1（内容不变）；
   * - 只有 `lock_node_ids` 里**明确列出**的节点会被标记 `locked`，
   *   服务端**不会**自己从攻略里挑已经 `locked` 的节点。
   *
   * 所以传空数组 = 确认但一个节点都不锁。这是 B7 的刻意取舍：
   * 契约里的 `locked` 是"这条改动不了"的用户意图（例如已订好的酒店），
   * 在页面还没有逐节点勾选之前，前端**不能替用户决定**锁哪些。
   * 要真的锁，得先把勾选做出来——这条已登记给 C 定夺，不在这里猜。
   *
   * 返回 `true` 表示确认成功（理由同 `reportIncidentNow`：别让调用方读 `error`）。
   */
  async function confirmCurrentGuide(): Promise<boolean> {
    const current = guide.value
    if (!current || loading.value) return false
    loading.value = true
    error.value = null
    try {
      const result = await confirmGuide(current.guide_id, {
        expected_guide_version: current.guide_version,
        lock_node_ids: [],
        idempotency_key: `confirm-${current.guide_id}-${current.guide_version}`,
      })
      guide.value = result.data.travel_guide
      guideOrigin.value = 'api'
      // confirm 只返回正文、不带谱系：上一轮改动记录对新版本已不适用。
      versionLineage.value = null
      lineageBaseGuide.value = null
      absorbWarnings(result.warnings)
      pushMessage(
        'assistant',
        `已确认这份攻略（版本 ${current.guide_version} → ${result.data.travel_guide.guide_version}）。`,
        stage.value,
      )
      persist()
      return true
    } catch (cause) {
      const described = describeError(cause)
      error.value = described
      pushMessage('assistant', `确认攻略没成功：${described.message}`)
      if (described.code === 'VERSION_CONFLICT') {
        await syncGuide(current.guide_id)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 上报突发（`POST /api/guides/{id}/incident`），触发重规划并拿回新版本。
   *
   * 与「聊天里直接说下雨了」是两条并行的入口：聊天那条由后端的
   * `detect_incident` 节点自动识别；这条是用户显式点「报个突发」时走的结构化通道。
   *
   * 返回 `true` 表示这次动作成功。**不要**让调用方去读 `store.error` 判成败：
   * `error` 可能残留自上一轮别的操作，读它会把旧错误当成本次失败报出来。
   */
  async function reportIncidentNow(rawText: string): Promise<boolean> {
    const current = guide.value
    const text = rawText.trim()
    if (!current || !text || loading.value) return false
    loading.value = true
    error.value = null
    const action: UserAction = {
      action_id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      idempotency_key: `incident-${current.guide_id}-${current.guide_version}-${text}`,
      action_type: 'REPORT_INCIDENT',
      session_id: current.session_id,
      guide_id: current.guide_id,
      expected_guide_version: current.guide_version,
      raw_text: text,
    }
    pushMessage('user', text)
    try {
      const result = await reportIncident(current.guide_id, action)
      guide.value = result.data.travel_guide
      guideOrigin.value = 'api'
      versionLineage.value = result.data.version_lineage
      // `current` 是改动前的那一版，正好拿来解析谱系里的旧节点 ID。
      lineageBaseGuide.value = current
      conflicts.value = result.data.conflicts ?? []
      absorbWarnings(result.warnings)
      pushMessage(
        'assistant',
        `已按突发重规划，攻略版本更新到 ${result.data.travel_guide.guide_version}。`,
        stage.value,
      )
      await refreshState()
      persist()
      return true
    } catch (cause) {
      const described = describeError(cause)
      error.value = described
      pushMessage('assistant', `上报突发没走通：${described.message}`)
      return false
    } finally {
      loading.value = false
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

  /**
   * 演示通道：把 `GUIDE_INCOMPLETE`（计划已验证通过、但攻略素材不足）单独亮出来。
   *
   * 为什么需要这条演示：这个阶段在真实数据上目前触发不到——A 补齐成都 Mock 覆盖后
   * `tools/check_b_flow.py --deps real` 会直接跑到 READY，而它只在**攻略组装**
   * 缺素材时出现（`graph/nodes.py`：组不出攻略就只回这个阶段，刻意不报 READY）。
   * 没有这条通道，新加的阶段处理就是一段永远走不到的代码，也没法演示。
   *
   * `degraded_items` 的文案对齐后端 `session_service` 的拼法
   * （`f"攻略暂时组装不了：{note}"`，note 来自 `guide_service.build_guide` 的
   * `GuideDataError`），但**整条状态是前端造出来的，不经过后端**。
   */
  async function loadGuideIncompleteDemo(): Promise<void> {
    stage.value = 'GUIDE_INCOMPLETE'
    guide.value = null
    guideOrigin.value = 'none'
    guideNotice.value = null
    versionLineage.value = null
    lineageBaseGuide.value = null
    conflicts.value = []
    warnings.value = []
    degradedItems.value = [
      '攻略暂时组装不了：缺少 2026-10-02 的抵达交通方案，无法填出抵达衔接。',
      '攻略暂时组装不了：缺少 2026-10-06 的返程交通方案，无法填出返程衔接。',
    ]
    demoNotice.value =
      '这是本地的 GUIDE_INCOMPLETE 预览：阶段与 degraded_items 的拼法与后端一致，但整条状态是前端造出来的，不经过后端。真实情况下这个阶段由攻略组装缺素材触发（计划本身有效）。'
    messages.value = []
    pushMessage('user', '就按你推荐的成都安排吧，确认', 'AWAITING_DESTINATION_CONFIRMATION')
    pushMessage(
      'assistant',
      '计划已经通过验证，但攻略还组装不出来：缺少攻略素材。补齐后我会直接出新版本。',
      'GUIDE_INCOMPLETE',
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
    versionLineage.value = null
    lineageBaseGuide.value = null
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
    versionLineage,
    lineageBaseGuide,
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
    confirmCurrentGuide,
    reportIncidentNow,
    loadFixtureDemo,
    loadFixtureClarificationDemo,
    loadGuideIncompleteDemo,
    dismissDemoNotice,
    dismissGuideNotice,
    dismissWarning,
    dismissDegraded,
    dismissError,
    reset,
  }
})
