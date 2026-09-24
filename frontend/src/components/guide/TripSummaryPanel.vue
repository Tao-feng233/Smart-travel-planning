<script setup lang="ts">
/** 第一部分：行程概览。 */
import type { TripSummarySection } from '@/types/contract'
import { formatDateRange, formatDuration } from '@/utils/format'

defineProps<{ section: TripSummarySection }>()
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">一、行程概览</h3>

    <p class="panel__theme">{{ section.overall_theme }}</p>
    <p class="ts-muted panel__reason">{{ section.overall_reason }}</p>

    <div class="panel__grid">
      <div class="ts-kv">
        <span class="ts-kv__k">目的地</span>
        <span class="ts-kv__v">{{ section.destination_names.join('、') || '—' }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">日期</span>
        <span class="ts-kv__v">{{ formatDateRange(section.start_date, section.end_date) }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">时长</span>
        <span class="ts-kv__v">{{ formatDuration(section.duration_days) }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">人数</span>
        <span class="ts-kv__v">{{ section.traveler_count }} 人</span>
      </div>
    </div>

    <el-alert
      v-if="section.major_tradeoffs.length > 0"
      class="panel__tradeoff"
      type="info"
      :closable="false"
      show-icon
      title="这份攻略做了这些取舍"
      :description="section.major_tradeoffs.join('；')"
    />
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.panel__theme {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.panel__reason {
  margin: 4px 0 10px;
  font-size: 13px;
}

.panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 18px;
}

.panel__tradeoff {
  margin-top: 10px;
}
</style>
