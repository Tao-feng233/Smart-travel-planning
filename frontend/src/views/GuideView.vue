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
import EvidencePanel from '@/components/guide/EvidencePanel.vue'
import GuideChangePanel from '@/components/guide/GuideChangePanel.vue'
import LodgingPanel from '@/components/guide/LodgingPanel.vue'
import PreparationPanel from '@/components/guide/PreparationPanel.vue'
import TripSummaryPanel from '@/components/guide/TripSummaryPanel.vue'
import { useSessionStore } from '@/stores/session'
import { stageProgress } from '@/utils/labels'

const store = useSessionStore()
const guide = computed(() => store.guide)

/** 突发描述。刻意不做模板/下拉：突发本来就是自由文本，交给后端识别。 */
const incidentText = ref('')

/** 计划已通过验证但攻略组不出来（`graph/stages.py` GUIDE_INCOMPLETE）。 */
const guideIncomplete = computed(() => store.stage === 'GUIDE_INCOMPLETE')

/**
 * 计划排出来了、但验证卡住时，空态该说的那句话。
 *
 * 这个状态和"还没开始"必须分开写：**它不会自己变好**，等下去也等不到攻略。
 * 所以不能沿用"等对话推进到「攻略已就绪」"那套文案——那个事件永远不会来。
 *
 * 有没有可选改法要分开说：后端给了 `repair_options` 就该让用户去挑，
 * 没给才是"要你自己确认"。两者混成一句话会让人以为有得选。
 */
const stalledFixText = computed(() =>
  store.conflicts.some((conflict) => conflict.repair_options.length > 0)
    ? '有的问题上面给了可选改法，你挑一个告诉我怎么改。'
    : '这一轮没有可自动执行的改法，需要你确认后告诉我怎么调整。',
)

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
      :run-mode="store.runMode"
    />

    <!--
      正在跑链路时给个看得见的进度：三块骨架条 + 当前进度话术。
      空状态文案说的是「攻略还没有生成」，在等待期间读起来像"没戏"，
      容易让用户以为要自己去点或者已经失败。
    -->
    <div v-if="store.loading" class="guide-loading">
      <div class="guide-loading__head">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>{{ stageProgress(store.stage) }}</span>
      </div>
      <div v-for="n in 3" :key="n" class="skeleton ts-card">
        <span class="skeleton__bar skeleton__bar--title"></span>
        <span class="skeleton__bar"></span>
        <span class="skeleton__bar skeleton__bar--short"></span>
      </div>
    </div>

    <div v-else class="ts-empty">
      <el-icon style="font-size: 28px"><MapLocation /></el-icon>

      <template v-if="guideIncomplete">
        <p>计划已经通过验证，但攻略还组装不出来。</p>
        <p class="ts-faint">
          这不是「再等等就好」：缺的是攻略素材，所以后端刻意不报「攻略已就绪」。<br />
          缺哪些素材见顶部那条黄色提示（后端未给出清单时会明说）。
        </p>
      </template>

      <!--
        计划排出来了、但验证没过：这一栏空着**不等于**「再等等」。
        必须和上面的冲突面板呼应，说清卡在哪、要用户做什么；
        否则用户会照旧文案去"等攻略已就绪"，而那个阶段永远不会来。
      -->
      <template v-else-if="store.conflicts.length > 0">
        <p>行程已经排出来了，但有几项必须先处理。</p>
        <p class="ts-faint">
          上面列出的问题没解决完，这份行程就不算通过验证，攻略也就不会生成。<br />
          {{ stalledFixText }}
        </p>
      </template>

      <template v-else>
        <p>攻略还没有生成。</p>
        <p class="ts-faint">
          在左边说清想去哪、从哪出发、什么时候走、几个人、大概预算，<br />
          等行程排好并通过验证，攻略就会出现在这里。
        </p>
      </template>
    </div>
  </template>

  <div v-else class="guide">
    <div class="guide__head">
      <div>
        <h2>{{ guide.trip_summary.destination_names.join(' · ') || '未命名行程' }}</h2>
        <!--
          真实模式下面向用户：只留「攻略第几版」这一条与人有关的版本信息。
          `plan_id` / `data_snapshot_id` / `timezone` 是给我们排障对齐用的，
          演示模式下保留（演示时要说清数据从哪来），真实模式收起。
        -->
        <p v-if="store.runMode === 'DEMO'" class="ts-faint">
          攻略 v{{ guide.guide_version }}｜计划 {{ guide.plan_id }} v{{ guide.plan_version }}｜
          数据快照 {{ guide.data_snapshot_id }}｜时区 {{ guide.timezone }}
        </p>
        <p v-else class="ts-faint">攻略第 {{ guide.guide_version }} 版</p>
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
      :run-mode="store.runMode"
    />

    <TripSummaryPanel :section="guide.trip_summary" />
    <ArrivalDeparturePanel :section="guide.arrival_and_departure" />
    <PreparationPanel :section="guide.preparation" />
    <LodgingPanel :section="guide.lodging" />
    <DailyItineraryPanel :days="guide.daily_itinerary" />
    <BudgetAlternativesPanel :section="guide.budget_and_alternatives" :run-mode="guide.run_mode" />
    <!-- L3 证据层：来源/时效/缺项默认收起，摘要行常显（信息分层，见 EvidencePanel 说明） -->
    <EvidencePanel :section="guide.sources_and_freshness" :missing="store.degradedItems" />
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

/* 等待攻略时的骨架 */
.guide-loading {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.guide-loading__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ts-text-weak);
}

.skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
}

.skeleton__bar {
  height: 10px;
  border-radius: 4px;
  background: var(--ts-surface-soft);
  animation: ts-pulse 1.4s ease-in-out infinite;
}

.skeleton__bar--title {
  height: 14px;
  width: 40%;
}

.skeleton__bar--short {
  width: 62%;
}

@keyframes ts-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton__bar {
    animation: none;
  }
}
</style>
