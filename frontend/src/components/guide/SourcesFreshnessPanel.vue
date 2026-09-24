<script setup lang="ts">
/**
 * 第七部分：数据来源与时效。
 *
 * 这一部分是整份攻略的"说明书"，也是三状态分离（ADR-0006）里
 * **数据可信度**那一条的具体呈现：哪些是核实过的、哪些是模拟的、
 * 哪些干脆没有数据，必须一眼看得见，不能拿旅游文案糊过去。
 */
import { computed } from 'vue'

import type { SourcesAndFreshnessSection } from '@/types/contract'
import { formatTimestamp } from '@/utils/format'
import { sourceItemLabel } from '@/utils/labels'

const props = defineProps<{ section: SourcesAndFreshnessSection }>()

const rows = computed(() => [
  {
    key: 'degraded',
    title: '降级项',
    hint: '数据源不可用，已用降级策略替代',
    tone: 'warning' as const,
    values: props.section.degraded_items.map(sourceItemLabel),
  },
  {
    key: 'mock',
    title: '模拟数据',
    hint: '演示模式下的占位数据，不能作为出行依据',
    tone: 'danger' as const,
    values: props.section.mock_items.map(sourceItemLabel),
  },
  {
    key: 'unknown',
    title: '暂无数据',
    hint: '这部分没有可用数据，攻略里对应位置不会给出结论',
    tone: 'info' as const,
    values: props.section.unknown_items.map(sourceItemLabel),
  },
])
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">七、数据来源与时效</h3>

    <div class="ts-kv">
      <span class="ts-kv__k">最后更新</span>
      <span class="ts-kv__v">{{ formatTimestamp(section.last_updated) }}</span>
    </div>
    <div class="ts-kv">
      <span class="ts-kv__k">事实记录</span>
      <span class="ts-kv__v ts-mono">
        {{ section.fact_record_ids.join('、') || '无（本攻略未引用事实记录）' }}
      </span>
    </div>
    <div class="ts-kv">
      <span class="ts-kv__k">证据</span>
      <span class="ts-kv__v ts-mono">
        {{ section.evidence_ids.join('、') || '无（本攻略未附带证据）' }}
      </span>
    </div>

    <div v-for="row in rows" :key="row.key" class="row">
      <div class="row__head">
        <el-tag size="small" :type="row.tone" effect="plain">{{ row.title }}</el-tag>
        <span class="ts-faint">{{ row.hint }}</span>
      </div>
      <div class="row__body">
        <template v-if="row.values.length > 0">
          <el-tag v-for="value in row.values" :key="value" size="small" effect="plain" class="row__tag">
            {{ value }}
          </el-tag>
        </template>
        <span v-else class="ts-faint">无</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.row {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--ts-border);
}

.row__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.row__body {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.row__tag {
  margin-right: 0;
}
</style>
