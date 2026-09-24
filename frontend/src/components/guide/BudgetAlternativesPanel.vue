<script setup lang="ts">
/**
 * 第六部分：预算与备选方案。
 *
 * 红线提醒（写进界面，不只写在注释里）：预算**只能由 `CostItem[]` 逐项复算**，
 * 这里的每个数字都来自后端 `BudgetSummary`，前端不做任何加减。
 * `min/max` 是"部分条目价格未知"导致的区间，不是"我们猜的价格区间"。
 */
import { computed } from 'vue'

import type { BudgetAndAlternativesSection, Money, RunMode } from '@/types/contract'
import { formatMinutes, formatMoney } from '@/utils/format'
import { alternativeTriggerLabel, costCategoryLabel } from '@/utils/labels'

const props = defineProps<{ section: BudgetAndAlternativesSection; runMode: RunMode }>()

const summary = computed(() => props.section.budget_summary)

const categories = computed(() =>
  Object.entries(summary.value.by_category ?? {})
    .filter(([, amount]) => amount > 0)
    .sort((a, b) => b[1] - a[1]),
)

const maxCategory = computed(() => Math.max(1, ...categories.value.map(([, amount]) => amount)))

function barWidth(amount: number): string {
  return `${Math.round((amount / maxCategory.value) * 100)}%`
}

function signedMoney(money: Money): string {
  const text = formatMoney(money)
  if (money.amount !== null && money.amount !== undefined) {
    return money.amount > 0 ? `+${text}` : text
  }
  return text
}
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">六、预算与备选方案</h3>

    <div class="summary">
      <div class="stat">
        <span class="stat__label">预算上限</span>
        <span class="stat__value">{{ summary.total_limit.toLocaleString('zh-CN') }} 元</span>
      </div>
      <div class="stat">
        <span class="stat__label">已确认花费</span>
        <span class="stat__value">{{ summary.known_total.toLocaleString('zh-CN') }} 元</span>
      </div>
      <div class="stat">
        <span class="stat__label">估算花费</span>
        <span class="stat__value">
          {{ summary.estimated_min_total.toLocaleString('zh-CN') }}
          <template v-if="summary.estimated_max_total !== summary.estimated_min_total">
            ~ {{ summary.estimated_max_total.toLocaleString('zh-CN') }}
          </template>
          元
        </span>
      </div>
      <div class="stat">
        <span class="stat__label">预计结余</span>
        <span class="stat__value">
          {{ summary.remaining_min.toLocaleString('zh-CN') }}
          <template v-if="summary.remaining_max !== summary.remaining_min">
            ~ {{ summary.remaining_max.toLocaleString('zh-CN') }}
          </template>
          元
        </span>
      </div>
    </div>

    <p class="ts-faint panel__note">
      以上数字由后端按 `CostItem[]` 逐项复算得出，模型不参与估算。
      运行模式：{{ runMode === 'DEMO' ? '演示（含模拟数据）' : '真实' }}。
    </p>

    <el-alert
      v-if="summary.unknown_cost_item_ids.length > 0"
      class="panel__warn"
      type="warning"
      :closable="false"
      show-icon
      title="有价格未知的条目，实际花费可能高于估算"
      :description="summary.unknown_cost_item_ids.join('、')"
    />

    <div v-if="categories.length > 0" class="bars">
      <div v-for="[category, amount] in categories" :key="category" class="bar">
        <span class="bar__name">{{ costCategoryLabel(category) }}</span>
        <div class="bar__track">
          <div class="bar__fill" :style="{ width: barWidth(amount) }"></div>
        </div>
        <span class="bar__value ts-mono">{{ amount.toLocaleString('zh-CN') }}</span>
      </div>
    </div>

    <div v-if="section.alternative_plans.length > 0" class="alts">
      <p class="alts__title">备选方案</p>
      <div v-for="plan in section.alternative_plans" :key="plan.alternative_plan_id" class="alt">
        <div class="alt__head">
          <el-tag size="small" type="info" effect="plain">{{ alternativeTriggerLabel(plan.trigger) }}</el-tag>
          <span class="ts-faint">
            时间 {{ plan.time_delta_minutes > 0 ? '+' : '' }}{{ formatMinutes(Math.abs(plan.time_delta_minutes)) }}
            ｜费用 {{ signedMoney(plan.cost_delta) }}
          </span>
          <el-tag v-if="plan.requires_user_confirmation" size="small" type="warning" effect="plain">需你确认</el-tag>
        </div>
        <p class="alt__reason">{{ plan.reason }}</p>
        <p class="ts-faint">涉及节点：{{ plan.affected_node_ids.join('、') || '—' }}</p>
      </div>
    </div>

    <p v-else class="ts-faint">暂无备选方案（计划尚未遇到需要绕开的情况）。</p>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.stat {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  background: var(--ts-surface-soft);
  border: 1px solid var(--ts-border);
  border-radius: 8px;
}

.stat__label {
  font-size: 12px;
  color: var(--ts-text-weak);
}

.stat__value {
  font-size: 17px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.panel__note {
  margin: 8px 0 0;
}

.panel__warn {
  margin-top: 8px;
}

.bars {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bar {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) 72px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.bar__name {
  color: var(--ts-text-weak);
}

.bar__track {
  height: 8px;
  background: #eef1f5;
  border-radius: 4px;
  overflow: hidden;
}

.bar__fill {
  height: 100%;
  background: linear-gradient(90deg, #4b9bff, #1f6feb);
}

.bar__value {
  text-align: right;
}

.alts {
  margin-top: 14px;
}

.alts__title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ts-text-weak);
}

.alt {
  padding: 8px 10px;
  border: 1px dashed var(--ts-border);
  border-radius: 8px;
}

.alt + .alt {
  margin-top: 6px;
}

.alt__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.alt__reason,
.alt p {
  margin: 4px 0 0;
  font-size: 12px;
}
</style>
