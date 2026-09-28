<script setup lang="ts">
/**
 * 对话面板：消息流 + 目的地候选 + 追问卡 + 输入框。
 *
 * 目的地候选是 B4 的可见产物，所以放在对话流里而不是藏进"状态"页——
 * 用户需要在"要不要去这个城市"这一层就参与决策，而不是等排完行程才看到。
 * 每个候选的理由、取舍、风险、证据条数都照原样展示，不做美化。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import ClarificationCard from '@/components/ClarificationCard.vue'
import { useSessionStore } from '@/stores/session'
import type { DestinationRecommendation } from '@/types/contract'
import { formatDateRange } from '@/utils/format'
import { stageLabel } from '@/utils/labels'

const emit = defineEmits<{ (e: 'goto-result', tab: 'guide' | 'state'): void }>()

const store = useSessionStore()
const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const inputRef = ref<{ focus: () => void } | null>(null)

/**
 * 修改建议 chips（纯前端渲染）：模板尾部故意留空，让用户补完数值再发。
 * 话术与后端 B5 的 `change_type` 识别词表对齐（预算/日期/去掉），
 * 提高一句话就被正确归类的概率。
 */
const modifyChips = [
  { label: '改预算', template: '把预算改成 ' },
  { label: '改日期', template: '把出发日期改到 ' },
  { label: '去掉某个安排', template: '把第 天的 ' },
] as const

/** 空对话时的开场示例：点击只预填输入框，用户可以改完再发。 */
const starterChips = [
  '国庆想去个有好吃的地方，从上海出发，两个人，玩四天，预算五千',
  '十一月中旬想找个暖和的地方躺平，不想打卡景点',
  '带 60 岁以上的爸妈出去玩，节奏要慢，交通要少走路',
] as const

function prefill(template: string): void {
  draft.value = template
  inputRef.value?.focus()
}

const canSend = computed(() => draft.value.trim().length > 0 && !store.loading)
const showClarify = computed(() => store.needsClarification && !store.loading)

/**
 * 开场引导的显示时机：`init()` 一定会先推一条欢迎消息，所以
 * `messages.length === 0` 永远不成立。真正的判据是「用户还没说过话」——
 * 欢迎消息在，但还没有任何用户消息时，把三个示例需求亮出来。
 */
const isFreshSession = computed(() => !store.messages.some((item) => item.role === 'user'))

const placeholder = computed(() => {
  if (!store.sessionId) return '正在创建会话…'
  if (store.needsClarification) return '也可以直接打字补充，例如：从上海出发，10月2号走，两个人，预算五千左右'
  return '继续告诉我想去哪、想怎么玩，或者要求改行程'
})

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

watch(() => store.messages.length, scrollToBottom)
watch(() => store.needsClarification, scrollToBottom)

async function send(): Promise<void> {
  if (!canSend.value) return
  const text = draft.value.trim()
  draft.value = ''
  await store.send(text)
  await scrollToBottom()
}

async function onSubmitClarify(text: string): Promise<void> {
  ElMessage.success('已提交补充')
  await store.send(text)
  await scrollToBottom()
}

function onKeydown(event: KeyboardEvent): void {
  // Ctrl / Cmd + Enter 发送，单独 Enter 换行
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void send()
  }
}

function evidenceHint(ids: string[]): string {
  return ids.length > 0 ? `${ids.length} 条证据` : '暂无证据'
}

/**
 * 候选卡片的标题。
 *
 * `name` 是 Q8 新增的可选字段（后端 `reply_builder` 已统一用目的地中文名填充），
 * 但 Provider 没给出名称时它是 `null` —— 那就回退显示 ID，
 * 而不是在前端编一个：目的地名是事实性内容，只能来自数据层。
 */
function candidateTitle(candidate: DestinationRecommendation): string {
  return candidate.name?.trim() || candidate.destination_id
}
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="chat__scroll">
      <!-- 空对话开场引导：用户还没说过话时，示例点击预填输入框 -->
      <div v-if="isFreshSession" class="welcome">
        <p class="ts-faint">可以这样说：</p>
        <div class="welcome__chips">
          <button
            v-for="starter in starterChips"
            :key="starter"
            type="button"
            class="chip"
            @click="prefill(starter)"
          >
            {{ starter }}
          </button>
        </div>
      </div>

      <template v-for="(message, index) in store.messages" :key="index">
        <!-- 用户消息：右侧气泡 -->
        <div v-if="message.role === 'user'" class="msg msg--user">
          <div class="msg__bubble">
            <p class="msg__text">{{ message.text }}</p>
            <div class="msg__meta">
              <span class="ts-faint">{{ message.at }}</span>
            </div>
          </div>
        </div>
        <!--
          助手消息：全宽扁平，不包气泡（主流 AI 聊天已弃气泡式助手消息）。
          内容限宽 72ch（可读性黄金行宽 65-80 字符），长文不顶满整栏。
        -->
        <div v-else class="msg msg--assistant">
          <p class="msg__text">{{ message.text }}</p>
          <div class="msg__meta">
            <span v-if="message.stage" class="msg__stage">{{ stageLabel(message.stage) }}</span>
            <span class="ts-faint">{{ message.at }}</span>
          </div>
        </div>
      </template>

      <!-- 目的地候选（B4 产物） -->
      <div v-if="store.destinationCandidates.length > 0" class="candidates">
        <p class="ts-section-title">目的地候选（{{ store.destinationCandidates.length }}）</p>
        <div
          v-for="candidate in store.destinationCandidates"
          :key="candidate.destination_id"
          class="candidate ts-card"
        >
          <div class="candidate__head">
            <strong>{{ candidateTitle(candidate) }}</strong>
            <span v-if="candidate.name" class="candidate__id">{{ candidate.destination_id }}</span>
            <el-tag v-if="candidate.suitable" size="small" type="success" effect="plain">适合</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">待定</el-tag>
            <el-tag size="small" effect="plain">建议 {{ candidate.suggested_days }} 天</el-tag>
          </div>
          <p v-if="candidate.reason" class="candidate__reason">{{ candidate.reason }}</p>
          <p v-if="candidate.tradeoffs.length > 0" class="ts-faint">
            取舍：{{ candidate.tradeoffs.join('；') }}
          </p>
          <p v-if="candidate.risk_flags.length > 0" class="candidate__risk">
            风险：{{ candidate.risk_flags.join('；') }}
          </p>
          <p class="ts-faint">{{ evidenceHint(candidate.evidence_ids) }}｜readiness: {{ candidate.readiness_id }}</p>
        </div>
      </div>

      <!-- 冲突（C6 之后才会真正产生，这里先把展示位留好） -->
      <div v-if="store.conflicts.length > 0" class="conflicts">
        <el-alert
          v-for="conflict in store.conflicts"
          :key="conflict.conflict_id"
          class="conflict"
          :type="conflict.severity === 'ERROR' ? 'error' : 'warning'"
          :closable="false"
          show-icon
          :title="conflict.message"
          :description="`范围：${conflict.scope}｜修复选项 ${conflict.repair_options.length} 个`"
        />
      </div>

      <!-- B3 追问卡 -->
      <ClarificationCard
        v-if="showClarify"
        :fields="store.missingFields"
        :loading="store.loading"
        @submit="onSubmitClarify"
      />

      <!--
        修改建议 chips：攻略生成后给出三个最高频的修改入口。
        沿用 B3 的既定决策——前端渲染、不调新 API；点击只是预填输入框，
        具体数值由用户补完后自己发送，发送走的一直是同一条消息通道。
      -->
      <div v-if="store.guide && !store.loading" class="chips">
        <span class="chips__label">想改这份攻略？</span>
        <button
          v-for="chip in modifyChips"
          :key="chip.label"
          type="button"
          class="chip"
          @click="prefill(chip.template)"
        >
          {{ chip.label }}
        </button>
      </div>

      <div v-if="store.loading" class="chat__loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在处理…</span>
      </div>
    </div>

    <div class="chat__input">
      <el-input
        ref="inputRef"
        v-model="draft"
        type="textarea"
        :rows="2"
        resize="none"
        :placeholder="placeholder"
        :disabled="!store.sessionId"
        @keydown="onKeydown"
      />
      <div class="chat__actions">
        <span class="ts-faint">Ctrl + Enter 发送</span>
        <div class="chat__actions-right">
          <el-button
            v-if="store.guide"
            size="small"
            plain
            @click="emit('goto-result', 'guide')"
          >
            查看攻略
          </el-button>
          <el-button type="primary" size="small" :disabled="!canSend" :loading="store.loading" @click="send">
            发送
          </el-button>
        </div>
      </div>
      <p v-if="store.tripProfile" class="ts-faint chat__profile">
        已确认画像 v{{ store.tripProfile.profile_version }}：
        {{ store.tripProfile.departure_city }} ·
        {{ formatDateRange(store.tripProfile.start_date, store.tripProfile.end_date) }} ·
        {{ store.tripProfile.traveler_count }} 人 · 预算 {{ store.tripProfile.budget.amount ?? '区间' }} 元
      </p>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.chat__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg {
  display: flex;
}

.msg--user {
  justify-content: flex-end;
}

/* 助手消息：全宽扁平，限宽 72ch（65-80 字符的可读性黄金行宽） */
.msg--assistant {
  flex-direction: column;
  max-width: 72ch;
  padding: 2px 4px;
}

.msg__bubble {
  max-width: 88%;
  padding: 8px 11px;
  border-radius: 10px;
  background: var(--ts-surface-soft);
  border: 1px solid var(--ts-border);
}

.msg--user .msg__bubble {
  background: var(--ts-brand);
  border-color: var(--ts-brand);
  color: #fff;
}

.msg__text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.msg__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  opacity: 0.75;
}

.msg__stage {
  font-size: 11px;
}

.candidates,
.conflicts {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.candidate {
  padding: 10px 12px;
}

.candidate:hover {
  border-color: var(--ts-brand);
}

.candidate__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 13px;
}

/* 有中文名时把 ID 收成小字附注（方便和后端返回对照）；没有名字时 ID 本身就是标题。 */
.candidate__id {
  font-size: 11px;
  color: var(--ts-text-weak);
}

.candidate__reason {
  margin: 6px 0 2px;
  font-size: 13px;
}

.candidate__risk {
  margin: 2px 0;
  font-size: 12px;
  color: var(--ts-danger);
}

.candidate p {
  margin: 2px 0;
}

.chat__loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.chat__input {
  border-top: 1px solid var(--ts-border);
  padding: 10px 12px;
  background: var(--ts-surface-soft);
}

.chat__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.chat__actions-right {
  display: flex;
  gap: 6px;
}

.chat__profile {
  margin: 6px 0 0;
}

/* 修改建议 chips */
.chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 空对话开场引导（跟在欢迎消息后面） */
.welcome {
  padding: 4px 2px;
}

.welcome__chips {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  margin-top: 6px;
}

.welcome__chips .chip {
  max-width: 92%;
  white-space: normal;
  line-height: 1.5;
  text-align: left;
}

.chips__label {
  font-size: 12px;
  color: var(--ts-text-faint);
}

.chip {
  padding: 5px 13px;
  font-size: 13px;
  color: var(--ts-text);
  background: var(--ts-surface);
  border: 1px solid var(--ts-border);
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.chip:hover {
  border-color: var(--ts-brand);
  color: var(--ts-brand);
}
</style>
