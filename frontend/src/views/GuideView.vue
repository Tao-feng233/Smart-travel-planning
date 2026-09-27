<script setup lang="ts">
/**
 * 右栏「行程攻略」：`TravelGuide` 的七部分装配结果。
 *
 * 顺序就是契约 §9 的顺序，不再重排——用户按"先知道这是什么行程、怎么去、
 * 带什么、住哪、每天怎么走、花多少钱、数据从哪来"读下去。
 *
 * 顶部的两个动作是攻略页唯一能改后端状态的地方，都走 §13.2 的接口：
 * 「就按这份走」= `confirm`（锁定节点、版本 +1）；「上报突发」= `incident`
 * （触发重规划，回来时带 `version_lineage` 与 `conflicts`）。
 * 也就是说：**先让用户看到攻略，再让用户对它做动作**，不在会话里偷偷改。
 */
import { computed, ref } from 'vue'

import { ElMessage } from 'element-plus'

import ArrivalDeparturePanel from '@/components/guide/ArrivalDeparturePanel.vue'
import BudgetAlternativesPanel from '@/components/guide/BudgetAlternativesPanel.vue'
import DailyItineraryPanel from '@/components/guide/DailyItineraryPanel.vue'
import GuideChangePanel from '@/components/guide/GuideChangePanel.vue'
import LodgingPanel from '@/components/guide/LodgingPanel.vue'
import PreparationPanel from '@/components/guide/PreparationPanel.vue'
import SourcesFreshnessPanel from '@/components/guide/SourcesFreshnessPanel.vue'
import TripSummaryPanel from '@/components/guide/TripSummaryPanel.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const guide = computed(() => store.guide)

/** 突发描述。刻意不做模板/下拉：突发本来就是自由文本，交给后端识别。 */
const incidentText = ref('')

/** 计划已通过验证但攻略组不出来（`graph/stages.py` GUIDE_INCOMPLETE）。 */
const guideIncomplete = computed(() => store.stage === 'GUIDE_INCOMPLETE')

/**
 * 没有攻略、但仍然有必须让用户看到的东西。
 *
 * 首次规划就卡在 `REPAIRING` 时（计划本身有问题、修不动），后端已经把
 * `conflicts` 带回来了，但那时**还没有攻略**（`data.guide_id` 为空）。
 * 若把冲突面板挂在"有没有攻略"下面，这些冲突会一条都显示不出来，
 * 用户会以为这份行程是干净的——所以这里单独判一次。
 */
const hasChangeInfo = computed(
  () => store.conflicts.length > 0 || Boolean(store.versionLineage),
)

/**
 * 哪个动作正在跑。
 *
 * 不能直接用 `store.loading` 驱动两个按钮的 loading：两个按钮会**同时**转圈，
 * 用户分不清是哪一次请求在跑。这里只让真正被点的那个转。
 */
const pending = ref<'confirm' | 'incident' | null>(null)

/** 已确认过的攻略不再重复确认（后端会因版本冲突拒绝，不如前端先说清）。 */
const canConfirm = computed(
  () => Boolean(guide.value) && guide.value?.lifecycle_status !== 'CONFIRMED',
)

async function onConfirm(): Promise<void> {
  if (pending.value) return
  pending.value = 'confirm'
  try {
    // 用返回值判成败，不看 `store.error`——它可能残留自上一轮别的操作。
    const done = await store.confirmCurrentGuide()
    if (done) {
      // 不断言"节点已锁定"：本次并不传 lock_node_ids，锁了才叫锁。
      ElMessage.success('已确认这份攻略（状态 CONFIRMED，版本 +1）')
    } else if (store.error) {
      ElMessage.error(`确认没成功：${store.error.message}`)
    }
  } finally {
    pending.value = null
  }
}

async function onIncident(): Promise<void> {
  const text = incidentText.value.trim()
  if (!text || pending.value) return
  pending.value = 'incident'
  try {
    const done = await store.reportIncidentNow(text)
    if (done) {
      incidentText.value = ''
      ElMessage.success('已按突发重规划，改动清单见「本轮改动」')
    } else if (store.error) {
      ElMessage.error(`上报没成功：${store.error.message}`)
    }
  } finally {
    pending.value = null
  }
}
</script>

<template>
  <template v-if="!guide">
    <!-- 有计划但没攻略时，conflicts 也必须露出来（见 `hasChangeInfo` 的说明）。 -->
    <GuideChangePanel
      v-if="hasChangeInfo"
      :guide="null"
      :previous-guide="null"
      :lineage="store.versionLineage"
      :conflicts="store.conflicts"
    />

    <div class="ts-empty">
      <el-icon style="font-size: 28px"><MapLocation /></el-icon>
      <template v-if="guideIncomplete">
        <p>计划已经通过验证，但攻略还组装不出来。</p>
        <p class="ts-faint">
          这不是「再等等就好」：缺的是攻略素材，所以后端刻意不报「攻略已就绪」。<br />
          缺哪些素材见顶部那条黄色提示（后端未给出清单时会明说）。
        </p>
      </template>
      <template v-else>
        <p>攻略还没有生成。</p>
        <p class="ts-faint">
          攻略由 C 线的规划与验证链路产出，B 线负责把验证过的计划组装成这七个部分。<br />
          在左侧把需求说清楚，等对话推进到「攻略已就绪」就会出现在这里。
        </p>
      </template>
    </div>
  </template>

  <div v-else class="guide">
    <div class="guide__head">
      <div>
        <h2>{{ guide.trip_summary.destination_names.join(' · ') || '未命名行程' }}</h2>
        <p class="ts-faint">
          攻略 v{{ guide.guide_version }}｜计划 {{ guide.plan_id }} v{{ guide.plan_version }}｜
          数据快照 {{ guide.data_snapshot_id }}｜时区 {{ guide.timezone }}
        </p>
      </div>

      <div class="guide__actions">
        <el-tooltip
          placement="top"
          content="确认后攻略状态变为 CONFIRMED、版本 +1。本页暂不支持逐节点勾选，所以确认不会锁定任何节点；突发重规划仍可能改到行程。"
        >
          <el-button
            size="small"
            :disabled="Boolean(pending) || !canConfirm"
            :loading="pending === 'confirm'"
            @click="onConfirm"
          >
            {{ canConfirm ? '就按这份走' : '已确认' }}
          </el-button>
        </el-tooltip>
        <el-input
          v-model="incidentText"
          class="guide__incident"
          size="small"
          placeholder="遇到突发？例如：今天下雨了"
          :disabled="Boolean(pending)"
          @keyup.enter="onIncident"
        />
        <el-button
          size="small"
          type="primary"
          :disabled="Boolean(pending) || !incidentText.trim()"
          :loading="pending === 'incident'"
          @click="onIncident"
        >
          上报突发
        </el-button>
      </div>
    </div>

    <GuideChangePanel
      :guide="guide"
      :previous-guide="store.lineageBaseGuide"
      :lineage="store.versionLineage"
      :conflicts="store.conflicts"
    />

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

.guide__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.guide__head h2 {
  margin: 0;
  font-size: 19px;
}

.guide__head p {
  margin: 4px 0 0;
}

.guide__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.guide__incident {
  width: 220px;
}
</style>
