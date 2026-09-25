<script setup lang="ts">
/**
 * 右栏「行程攻略」：`TravelGuide` 的七部分装配结果。
 *
 * 顺序就是契约 §9 的顺序，不再重排——用户按"先知道这是什么行程、怎么去、
 * 带什么、住哪、每天怎么走、花多少钱、数据从哪来"读下去。
 */
import { computed } from 'vue'

import ArrivalDeparturePanel from '@/components/guide/ArrivalDeparturePanel.vue'
import BudgetAlternativesPanel from '@/components/guide/BudgetAlternativesPanel.vue'
import DailyItineraryPanel from '@/components/guide/DailyItineraryPanel.vue'
import LodgingPanel from '@/components/guide/LodgingPanel.vue'
import PreparationPanel from '@/components/guide/PreparationPanel.vue'
import SourcesFreshnessPanel from '@/components/guide/SourcesFreshnessPanel.vue'
import TripSummaryPanel from '@/components/guide/TripSummaryPanel.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const guide = computed(() => store.guide)
</script>

<template>
  <div v-if="!guide" class="ts-empty">
    <el-icon style="font-size: 28px"><MapLocation /></el-icon>
    <p>攻略还没有生成。</p>
    <p class="ts-faint">
      攻略由 C 线的规划与验证链路产出，B 线负责把验证过的计划组装成这七个部分。<br />
      在左侧把需求说清楚，等对话推进到「攻略已就绪」就会出现在这里。
    </p>
  </div>

  <div v-else class="guide">
    <div class="guide__head">
      <div>
        <h2>{{ guide.trip_summary.destination_names.join(' · ') || '未命名行程' }}</h2>
        <p class="ts-faint">
          攻略 v{{ guide.guide_version }}｜计划 {{ guide.plan_id }} v{{ guide.plan_version }}｜
          数据快照 {{ guide.data_snapshot_id }}｜时区 {{ guide.timezone }}
        </p>
      </div>
    </div>

    <TripSummaryPanel :section="guide.trip_summary" />
    <ArrivalDeparturePanel :section="guide.arrival_and_departure" />
    <PreparationPanel :section="guide.preparation" />
    <LodgingPanel :section="guide.lodging" />
    <DailyItineraryPanel :days="guide.daily_itinerary" />
    <BudgetAlternativesPanel :section="guide.budget_and_alternatives" :run-mode="guide.run_mode" />
    <SourcesFreshnessPanel :section="guide.sources_and_freshness" />
  </div>
</template>

<style scoped>
.guide {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.guide__head h2 {
  margin: 0;
  font-size: 19px;
}

.guide__head p {
  margin: 4px 0 0;
}
</style>
