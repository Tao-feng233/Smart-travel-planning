<script setup lang="ts">
/**
 * B3 的界面落点：把后端的追问清单渲染成"点几下就能答完"的结构化表单。
 *
 * 设计取舍：
 * - **不新增接口**。表单最终合成一句自然语言，走原来的 `POST /messages`。
 *   这样前端自由输入与点选表单是同一条后端链路，不会出现两套解析行为。
 * - **不替后端做判断**。哪些字段缺由后端 warning 决定，前端只负责收集；
 *   用户想只答其中一两项也可以，剩下的下一轮还会继续问。
 * - 预算按用户拍板的方案做档位选择器，但档位值**原样上报**，
 *   不做"打包价"之类的换算（预算只能由 `CostItem[]` 复算，前端不得参与）。
 */
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  BUDGET_LOW_TIERS,
  BUDGET_TIERS,
  buildClarificationMessage,
  emptyForm,
  fieldMeta,
  isFormEmpty,
  type ClarificationForm,
} from '@/utils/clarification'

const props = defineProps<{ fields: string[]; loading?: boolean }>()
const emit = defineEmits<{ (e: 'submit', text: string): void }>()

const form = reactive<ClarificationForm>(emptyForm())
const submitting = ref(false)

const metas = computed(() => props.fields.map((name) => fieldMeta(name)))
const budgetSelected = computed(() => form.budget)
const canSubmit = computed(() => !isFormEmpty(form) && !submitting.value && !props.loading)

function pickText(name: string, value: string): void {
  form.text[name] = value
}

function pickCount(value: number): void {
  form.traveler_count = form.traveler_count === value ? null : value
}

function pickBudget(amount: number): void {
  form.budget = form.budget === amount ? null : amount
}

function disablePast(date: Date): boolean {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}

function disableBeforeStart(date: Date): boolean {
  const start = form.text.start_date
  if (!start) return disablePast(date)
  return date.getTime() < new Date(`${start}T00:00:00`).getTime()
}

function submit(): void {
  const text = buildClarificationMessage(form)
  if (!text.trim()) {
    ElMessage.warning('至少填一项再提交')
    return
  }
  submitting.value = true
  emit('submit', text)
  // 提交后不清空：后端若判定仍缺字段会再次追问，用户能接着补
  setTimeout(() => {
    submitting.value = false
  }, 400)
}

function resetForm(): void {
  Object.assign(form, emptyForm())
}
</script>

<template>
  <div class="clarify ts-card">
    <div class="clarify__head">
      <el-icon class="clarify__icon"><ChatDotRound /></el-icon>
      <div>
        <h3>还需要确认 {{ metas.length }} 件事</h3>
        <p class="ts-faint">点选或填写后提交，也可以直接在下方输入框里自己说。</p>
      </div>
    </div>

    <div v-for="meta in metas" :key="meta.name" class="clarify__field">
      <label class="clarify__label">
        {{ meta.label }}
        <span class="clarify__question">{{ meta.question }}</span>
      </label>

      <!-- 文本 -->
      <template v-if="meta.kind === 'text'">
        <el-input
          v-model="form.text[meta.name]"
          size="small"
          :placeholder="meta.placeholder"
          clearable
          @keyup.enter="submit"
        />
        <div v-if="meta.quickPicks?.length" class="clarify__chips">
          <el-button
            v-for="option in meta.quickPicks"
            :key="option"
            size="small"
            plain
            :type="form.text[meta.name] === option ? 'primary' : 'default'"
            @click="pickText(meta.name, option)"
          >
            {{ option }}
          </el-button>
        </div>
      </template>

      <!-- 日期 -->
      <template v-else-if="meta.kind === 'date'">
        <el-date-picker
          v-model="form.text[meta.name]"
          type="date"
          size="small"
          value-format="YYYY-MM-DD"
          format="YYYY-MM-DD"
          placeholder="选择日期"
          :disabled-date="meta.name === 'end_date' ? disableBeforeStart : disablePast"
          style="width: 100%"
        />
        <p v-if="meta.name === 'end_date'" class="ts-faint clarify__hint">
          不知道具体日期也行，用下面的"玩几天"告诉我就够。
        </p>
      </template>

      <!-- 人数 -->
      <template v-else-if="meta.kind === 'number'">
        <el-input-number v-model="form.traveler_count" size="small" :min="1" :max="30" />
        <div class="clarify__chips">
          <el-button
            v-for="option in meta.quickPicks ?? []"
            :key="option"
            size="small"
            plain
            :type="form.traveler_count === Number(option) ? 'primary' : 'default'"
            @click="pickCount(Number(option))"
          >
            {{ option }} 人
          </el-button>
        </div>
      </template>

      <!-- 预算：档位选择器 -->
      <template v-else-if="meta.kind === 'budget'">
        <div class="clarify__chips">
          <el-button
            v-for="tier in BUDGET_LOW_TIERS"
            :key="tier.amount"
            size="small"
            plain
            :type="budgetSelected === tier.amount ? 'primary' : 'default'"
            @click="pickBudget(tier.amount)"
          >
            {{ tier.amount }} 元
          </el-button>
        </div>
        <div class="clarify__tiers">
          <button
            v-for="tier in BUDGET_TIERS"
            :key="tier.amount"
            type="button"
            class="tier"
            :class="{ 'tier--on': budgetSelected === tier.amount }"
            @click="pickBudget(tier.amount)"
          >
            <span class="tier__amount">{{ tier.amount.toLocaleString('zh-CN') }}</span>
            <span class="tier__hint">{{ tier.hint }}</span>
          </button>
        </div>

        <div class="clarify__budget-extra">
          <span class="ts-faint">更高额度直接填：</span>
          <el-input-number v-model="form.budget" size="small" :min="500" :step="500" :max="1000000" />
          <el-radio-group v-model="form.budgetFlexible" size="small">
            <el-radio-button value="NEGOTIABLE">可浮动</el-radio-button>
            <el-radio-button value="FIXED">不能超</el-radio-button>
          </el-radio-group>
        </div>
      </template>
    </div>

    <!-- 只记得"玩几天"的情况 -->
    <div class="clarify__field">
      <label class="clarify__label">
        玩几天 <span class="clarify__question">没有确切返程日期时用这个</span>
      </label>
      <el-input-number v-model="form.days" size="small" :min="1" :max="30" />
      <span class="ts-faint">天</span>
    </div>

    <div class="clarify__actions">
      <el-button type="primary" size="small" :disabled="!canSubmit" :loading="submitting" @click="submit">
        提交补充
      </el-button>
      <el-button size="small" text @click="resetForm">清空</el-button>
      <span class="ts-faint">只会把填写过的项目发出去</span>
    </div>
  </div>
</template>

<style scoped>
.clarify {
  padding: 14px;
  background: var(--ts-brand-soft);
  border-color: #cfe0ff;
}

.clarify__head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.clarify__icon {
  margin-top: 3px;
  color: var(--ts-brand);
  font-size: 18px;
}

.clarify__head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.clarify__head p {
  margin: 2px 0 0;
}

.clarify__field {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-top: 1px dashed #d5e2fb;
}

.clarify__field:first-of-type {
  border-top: none;
}

.clarify__label {
  flex: 0 0 92px;
  font-size: 13px;
  font-weight: 600;
  color: #24405f;
}

.clarify__question {
  display: block;
  font-weight: 400;
  font-size: 11px;
  color: var(--ts-text-weak);
}

.clarify__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.clarify__chips :deep(.el-button + .el-button) {
  margin-left: 0;
}

.clarify__hint {
  flex-basis: 100%;
  margin: 0;
}

.clarify__tiers {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  gap: 6px;
  width: 100%;
}

.tier {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 6px 9px;
  background: #fff;
  border: 1px solid var(--ts-border);
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.tier:hover {
  border-color: #a9c8ff;
}

.tier--on {
  border-color: var(--ts-brand);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.14);
}

.tier__amount {
  font-size: 13px;
  font-weight: 600;
  color: var(--ts-text);
}

.tier__hint {
  font-size: 11px;
  color: var(--ts-text-faint);
}

.clarify__budget-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex-basis: 100%;
}

.clarify__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #d5e2fb;
}
</style>
