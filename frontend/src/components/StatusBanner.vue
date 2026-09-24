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
</script>

<template>
  <div class="banner">
    <div class="banner__row">
      <el-tag size="small" effect="plain">阶段：{{ stageLabel(store.stage) }}</el-tag>

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

    <el-alert
      v-if="store.visibleDegradedItems.length > 0"
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
