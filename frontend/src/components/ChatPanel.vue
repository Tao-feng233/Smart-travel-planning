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
import { formatDateRange } from '@/utils/format'
import { stageLabel } from '@/utils/labels'

const emit = defineEmits<{ (e: 'goto-result', tab: 'guide' | 'state'): void }>()

const store = useSessionStore()
const draft = ref('')
const scroller = ref<HTMLElement | null>(null)

const canSend = computed(() => draft.value.trim().length > 0 && !store.loading)
const showClarify = computed(() => store.needsClarification && !store.loading)

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
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="chat__scroll">
      <!-- 空对话 -->
      <div v-if="store.messages.length === 0" class="ts-empty">
        <p>还没有对话。</p>
        <p class="ts-faint">试试：「国庆想去个有好吃的地方，从上海出发，两个人，玩四天，预算五千」</p>
      </div>

      <div
        v-for="(message, index) in store.messages"
        :key="index"
        class="msg"
        :class="message.role === 'user' ? 'msg--user' : 'msg--assistant'"
      >
        <div class="msg__bubble">
          <p class="msg__text">{{ message.text }}</p>
          <div class="msg__meta">
            <span v-if="message.stage" class="msg__stage">{{ stageLabel(message.stage) }}</span>
            <span class="ts-faint">{{ message.at }}</span>
          </div>
        </div>
      </div>

      <!-- 目的地候选（B4 产物） -->
      <div v-if="store.destinationCandidates.length > 0" class="candidates">
        <p class="ts-section-title">目的地候选（{{ store.destinationCandidates.length }}）</p>
        <div
          v-for="candidate in store.destinationCandidates"
          :key="candidate.destination_id"
          class="candidate ts-card"
        >
          <div class="candidate__head">
            <strong>{{ candidate.destination_id }}</strong>
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

      <div v-if="store.loading" class="chat__loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在处理…</span>
      </div>
    </div>

    <div class="chat__input">
      <el-input
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

.candidate__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 13px;
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
</style>
