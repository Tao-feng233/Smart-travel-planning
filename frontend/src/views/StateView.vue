<script setup lang="ts">
/**
 * 右栏「运行状态」：排查与演示用，不是给游客看的页面。
 *
 * 三块内容：
 * 1. `PlanState` —— LangGraph 的权威状态（只存 ID 与版本，不存业务对象）
 * 2. `TripProfile` —— 已定稿的画像（含 Draft 阶段缺什么）
 * 3. 信封里的 `warnings` 原始内容 —— 不做美化，原文照贴，方便对齐后端
 */
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'
import { formatComposition, formatDate, formatMoney, orDash } from '@/utils/format'
import { warningTitle } from '@/utils/labels'

const store = useSessionStore()

const state = computed(() => store.planState)
const profile = computed(() => store.tripProfile)

const planStateRows = computed(() => {
  const value = state.value
  if (!value) return []
  return [
    ['会话', value.session_id],
    ['阶段', value.stage],
    ['画像版本', `v${value.trip_profile_version}`],
    ['目的地候选', value.destination_candidate_ids.length],
    ['资源候选', value.resource_candidate_ids.length],
    ['当前计划', value.current_plan_id ? `${value.current_plan_id} v${value.current_plan_version}` : '—'],
    ['当前攻略', value.current_guide_id ? `${value.current_guide_id} v${value.current_guide_version}` : '—'],
    ['锁定节点', orDash(value.locked_node_ids)],
    ['已完成节点', orDash(value.completed_node_ids)],
    ['冲突', orDash(value.conflict_ids)],
    ['活动事件', orDash(value.active_incidents)],
    ['数据快照', value.data_snapshot_id ?? '—'],
    ['修复尝试', String(value.repair_attempts)],
    ['等待用户', value.awaiting_user_input ? '是' : '否'],
  ] as [string, string][]
})
</script>

<template>
  <div class="state">
    <section class="ts-card panel">
      <h3 class="ts-section-title">LangGraph 状态（PlanState）</h3>
      <div v-if="!state" class="ts-faint">还没有会话状态。</div>
      <div v-else class="grid">
        <div v-for="[key, value] in planStateRows" :key="key" class="ts-kv">
          <span class="ts-kv__k">{{ key }}</span>
          <span class="ts-kv__v ts-mono">{{ value }}</span>
        </div>
      </div>
    </section>

    <section class="ts-card panel">
      <h3 class="ts-section-title">旅行画像（TripProfile）</h3>
      <div v-if="!profile" class="ts-faint">
        画像还没有定稿。补齐关键字段后才会生成正式的 TripProfile。
      </div>
      <div v-else class="grid">
        <div class="ts-kv">
          <span class="ts-kv__k">出发地</span>
          <span class="ts-kv__v">{{ profile.departure_city }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">日期</span>
          <span class="ts-kv__v">
            {{ formatDate(profile.start_date) }} - {{ formatDate(profile.end_date) }}（{{ profile.duration_days }} 天）
          </span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">人数构成</span>
          <span class="ts-kv__v">{{ profile.traveler_count }} 人 · {{ formatComposition(profile.traveler_composition) }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">预算</span>
          <span class="ts-kv__v">
            {{ formatMoney(profile.budget) }}（{{ profile.budget_flexibility === 'FIXED' ? '不可超' : '可浮动' }}）
          </span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">节奏</span>
          <span class="ts-kv__v">{{ profile.pace }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">兴趣</span>
          <span class="ts-kv__v">{{ orDash(profile.interests) }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">避开</span>
          <span class="ts-kv__v">{{ orDash(profile.avoidances) }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">饮食限制</span>
          <span class="ts-kv__v">{{ orDash(profile.dietary_constraints) }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">目的地模式</span>
          <span class="ts-kv__v">{{ profile.destination_mode }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">点名目的地</span>
          <span class="ts-kv__v">{{ profile.destination_requests.map((item) => item.name).join('、') || '—' }}</span>
        </div>
      </div>

      <div v-if="profile?.constraints?.length" class="constraints">
        <p class="constraints__title">约束（模型标的 FIXED / NEGOTIABLE_HARD 一律降级为 SOFT）</p>
        <div v-for="item in profile.constraints" :key="item.constraint_id" class="constraint">
          <el-tag size="small" effect="plain">{{ item.kind }}</el-tag>
          <span class="ts-mono">{{ item.field }} {{ item.operator }} {{ item.value }}</span>
          <span v-if="item.source_text" class="ts-faint">「{{ item.source_text }}」</span>
        </div>
      </div>
    </section>

    <section class="ts-card panel">
      <h3 class="ts-section-title">信封 warnings（原文）</h3>
      <div v-if="store.warnings.length === 0" class="ts-faint">本轮没有 warning。</div>
      <div v-for="item in store.warnings" :key="item.code + item.message" class="warning">
        <div class="warning__head">
          <el-tag size="small" type="warning" effect="plain">{{ item.code }}</el-tag>
          <span>{{ warningTitle(item.code) }}</span>
        </div>
        <p class="warning__body">{{ item.message }}</p>
        <pre v-if="Object.keys(item.details ?? {}).length" class="warning__details ts-mono">{{
          JSON.stringify(item.details, null, 2)
        }}</pre>
      </div>
    </section>

    <section class="ts-card panel">
      <h3 class="ts-section-title">降级项</h3>
      <div v-if="store.degradedItems.length === 0" class="ts-faint">
        本轮没有降级。LLM 通道不可用时会自动回落到规则式实现，并把原因记在这里。
      </div>
      <ul v-else class="list">
        <li v-for="item in store.degradedItems" :key="item">{{ item }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.state {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel {
  padding: 14px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 0 18px;
}

.constraints {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--ts-border);
}

.constraints__title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ts-text-weak);
}

.constraint {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  padding: 2px 0;
}

.warning + .warning {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--ts-border);
}

.warning__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.warning__body {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.warning__details {
  margin: 4px 0 0;
  padding: 8px;
  background: var(--ts-surface-soft);
  border-radius: 6px;
  overflow: auto;
}

.list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
