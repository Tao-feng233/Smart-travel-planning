<script setup lang="ts">
/**
 * 证据折叠区（信息分层里的 L3）：数据来源与时效 + 攻略缺项提醒。
 *
 * 默认只渲染一行摘要（最后更新 + 各类数据计数 + 缺项条数），
 * 点开才看明细 —— 证据是"备查"性质，不该和行程主体抢视线；
 * 但摘要行本身一直在，因为数据可信度是这个项目的卖点：
 * 哪些是核实数据、哪些是模拟、哪些没有，用户随时一眼看得见。
 *
 * `missing` 是 `GUIDE_MATERIAL_MISSING` warning 还原出的缺项清单
 * （C 不新增契约字段，走信封 warnings 通道，见 `stores/session.ts`）。
 */
import { computed, ref } from 'vue'

import type { SourcesAndFreshnessSection } from '@/types/contract'
import { formatTimestamp } from '@/utils/format'

import SourcesFreshnessPanel from './SourcesFreshnessPanel.vue'

const props = defineProps<{
  section: SourcesAndFreshnessSection
  missing: string[]
}>()

const open = ref(false)

const summary = computed(() => {
  const parts = [
    `最后更新 ${formatTimestamp(props.section.last_updated)}`,
    `降级 ${props.section.degraded_items.length}`,
    `模拟 ${props.section.mock_items.length}`,
    `暂无数据 ${props.section.unknown_items.length}`,
  ]
  if (props.missing.length > 0) parts.push(`缺项提醒 ${props.missing.length}`)
  return parts.join(' · ')
})
</script>

<template>
  <section class="ts-card evidence">
    <button
      type="button"
      class="evidence__toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="evidence__chevron" :class="{ 'evidence__chevron--open': open }">▸</span>
      <span class="evidence__title">数据来源与提醒</span>
      <span class="ts-faint">{{ summary }}</span>
    </button>

    <div v-if="open" class="evidence__body">
      <template v-if="missing.length > 0">
        <el-alert
          v-for="item in missing"
          :key="item"
          class="evidence__missing"
          type="warning"
          :closable="false"
          show-icon
          :title="item"
        />
      </template>
      <SourcesFreshnessPanel :section="section" />
    </div>
  </section>
</template>

<style scoped>
.evidence {
  padding: 10px 14px;
}

.evidence__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
  padding: 0;
  font: inherit;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
}

.evidence__chevron {
  display: inline-block;
  font-size: 11px;
  color: var(--ts-text-faint);
  transition: transform 0.15s;
}

.evidence__chevron--open {
  transform: rotate(90deg);
}

.evidence__title {
  font-size: 13px;
  font-weight: 600;
}

.evidence__body {
  margin-top: 10px;
}

.evidence__missing {
  margin-bottom: 8px;
}

/* 明细里的第七部分卡片不再带外框阴影，避免"卡里套卡" */
.evidence__body :deep(.ts-card) {
  border: none;
  box-shadow: none;
  padding: 0;
}
</style>
