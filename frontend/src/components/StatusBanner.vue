<script setup lang="ts">
/**
 * 全局状态条：把"现在到哪一步、有哪些必须知情的事"集中说清楚。
 *
 * 这一块是项目的诚实性门面（`CONTRACTS.md` §9 / ADR-0006）：
 * 计划可行性、数据可信度、攻略生命周期是**三个独立状态**，不能互相代替，
 * 所以这里并列展示，压缩成一个"是否可用"的绿点。
 */
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'
import {
  dataAssuranceLabel,
  guideReadinessLabel,
  lifecycleLabel,
  planValidationLabel,
  stageLabel,
  warningTitle,
} from '@/utils/labels'

const store = useSessionStore()

const readinessType = computed(() => {
  const readiness = store.guide?.guide_readiness
  if (readiness === 'READY') return 'success'
  if (readiness === 'READY_WITH_WARNINGS') return 'warning'
  return 'danger'
})

const assuranceType = computed(() => {
  const status = store.guide?.data_assurance_status
  if (status === 'VERIFIED') return 'success'
  if (status === 'MOCK' || status === 'INSUFFICIENT') return 'danger'
  return 'warning'
})

const planType = computed(() => {
  const status = store.guide?.plan_validation_status
  if (status === 'VALID') return 'success'
  if (status === 'INVALID') return 'danger'
  return 'info'
})

const showGuideStatus = computed(() => Boolean(store.guide))

/**
 * 阶段标签的配色。
 *
 * `GUIDE_INCOMPLETE` 与 `INSUFFICIENT_DATA` 都不是「一切正常」，不能和
 * 进度类阶段混成同一种灰蓝：
 * - `GUIDE_INCOMPLETE`：计划已验证通过，但攻略组装缺素材，后端**刻意**不报 READY
 *   （`graph/nodes.py` 组不出攻略时只回这个阶段），所以它是「停住了」；
 * - `INSUFFICIENT_DATA`：知识库覆盖不足，同样是一个明确的终点而不是过渡态。
 */
const stageTagType = computed(() => {
  if (store.stage === 'GUIDE_INCOMPLETE') return 'warning'
  if (store.stage === 'INSUFFICIENT_DATA') return 'danger'
  return 'primary'
})

const guideIncomplete = computed(() => store.stage === 'GUIDE_INCOMPLETE')

/**
 * `GUIDE_INCOMPLETE` 的缺失清单。
 *
 * 用**原始** `degradedItems` 而不是已过滤的 `visibleDegradedItems`：
 * 这条提示描述的是「当前阶段」这个持续状态，不是某一轮的一次性提醒。
 * 用户点掉过一次降级提示，不能因此让"缺什么"永远消失——那样页面会变成
 * 看着像正常的空白页。
 */
const guideIncompleteText = computed(() => {
  const items = store.degradedItems
  return items.length
    ? `缺的是攻略素材，不是行程本身：${items.join('；')}`
    : '后端只标了阶段，没有给出缺失清单。'
})
</script>

<template>
  <div class="banner">
    <div class="banner__row">
      <el-tag size="small" :type="stageTagType" effect="plain">阶段：{{ stageLabel(store.stage) }}</el-tag>

      <template v-if="showGuideStatus">
        <el-tag size="small" :type="readinessType" effect="light">
          {{ guideReadinessLabel(store.guide?.guide_readiness) }}
        </el-tag>
        <el-tag size="small" :type="planType" effect="plain">
          {{ planValidationLabel(store.guide?.plan_validation_status) }}
        </el-tag>
        <el-tag size="small" :type="assuranceType" effect="plain">
          {{ dataAssuranceLabel(store.guide?.data_assurance_status) }}
        </el-tag>
        <el-tag size="small" type="info" effect="plain">
          {{ lifecycleLabel(store.guide?.lifecycle_status) }}
        </el-tag>
      </template>

      <el-tag v-if="store.mockInUse" size="small" type="warning" effect="plain">含模拟数据</el-tag>
      <span v-if="store.traceId" class="banner__trace ts-mono">trace: {{ store.traceId }}</span>
    </div>

    <el-alert
      v-if="store.error"
      class="banner__alert"
      type="error"
      :closable="true"
      show-icon
      :title="`${store.error.code}｜${store.error.message}`"
      @close="store.dismissError()"
    />

    <el-alert
      v-for="item in store.visibleWarnings"
      :key="store.warningKeyOf(item)"
      class="banner__alert"
      type="warning"
      :closable="true"
      show-icon
      :title="warningTitle(item.code)"
      :description="item.message"
      @close="store.dismissWarning(item)"
    />

    <el-alert
      v-if="store.demoNotice"
      class="banner__alert"
      type="info"
      :closable="true"
      show-icon
      title="本地演示状态"
      :description="store.demoNotice"
      @close="store.dismissDemoNotice()"
    />

    <el-alert
      v-if="store.guideNotice"
      class="banner__alert"
      type="info"
      :closable="true"
      show-icon
      title="攻略数据来源说明"
      :description="store.guideNotice"
      @close="store.dismissGuideNotice()"
    />

    <!-- 刻意不可关闭：它描述的是「当前阶段」，不是某一轮的一次性提醒。
         用户关不掉才不会被一个像正常页面的空白攻略页误导。 -->
    <el-alert
      v-if="guideIncomplete"
      class="banner__alert"
      type="warning"
      :closable="false"
      show-icon
      title="计划已经通过验证，但攻略还组装不出来"
      :description="guideIncompleteText"
    />

    <!-- 上面那条已经把这个阶段的 degraded_items 原样列过一次，不重复列第二遍。 -->
    <el-alert
      v-if="store.visibleDegradedItems.length > 0 && !guideIncomplete"
      class="banner__alert"
      type="warning"
      :closable="true"
      show-icon
      title="本轮有降级项"
      :description="store.visibleDegradedItems.join('；')"
      @close="store.dismissDegraded()"
    />
  </div>
</template>

<style scoped>
.banner {
  padding: 0 14px;
}

.banner:not(:empty) {
  padding-top: 10px;
}

.banner__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.banner__trace {
  margin-left: auto;
  color: var(--ts-text-faint);
}

.banner__alert {
  margin-top: 8px;
}
</style>
