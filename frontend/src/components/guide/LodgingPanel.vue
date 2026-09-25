<script setup lang="ts">
/**
 * 第四部分：住宿。
 *
 * `availability_is_realtime` 必须显式标出来：契约里住宿库存默认不是实时的，
 * 这个字段就是防止用户以为"页面上写了就一定能订到"。
 */
import { computed } from 'vue'

import type { LodgingCandidate, LodgingSection } from '@/types/contract'
import { formatDateRange, formatMoney } from '@/utils/format'
import { lodgingTypeLabel, qualityFlagLabel } from '@/utils/labels'

const props = defineProps<{ section: LodgingSection }>()

interface StayRow {
  id: string
  checkIn: string
  checkOut: string
  area: string
  userBooked: boolean
  locked: boolean
  switchReason: string | null
  /** 找不到候选详情时不编造，留空由界面提示 */
  candidate: LodgingCandidate | null
}

const stayRows = computed<StayRow[]>(() =>
  props.section.stay_segments.map((segment) => ({
    id: segment.stay_segment_id,
    checkIn: segment.check_in_date,
    checkOut: segment.check_out_date,
    area: segment.lodging_area,
    userBooked: segment.is_user_booked,
    locked: segment.locked,
    switchReason: segment.switch_reason,
    candidate: props.section.primary_candidates.find((item) => item.resource_id === segment.lodging_id) ?? null,
  })),
)
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">四、住在哪</h3>

    <div v-if="stayRows.length === 0" class="ts-faint">还没有确定住宿段落。</div>

    <div v-for="row in stayRows" :key="row.id" class="stay">
      <div class="stay__head">
        <strong>{{ formatDateRange(row.checkIn, row.checkOut) }}</strong>
        <el-tag size="small" effect="plain">{{ row.area }}</el-tag>
        <el-tag v-if="row.userBooked" size="small" type="success" effect="plain">用户自订</el-tag>
        <el-tag v-if="row.locked" size="small" type="info" effect="plain">已锁定</el-tag>
      </div>
      <p v-if="row.switchReason" class="ts-faint">换住原因：{{ row.switchReason }}</p>

      <div v-if="row.candidate" class="candidate">
        <div class="candidate__head">
          <span class="candidate__name">{{ row.candidate.name }}</span>
          <el-tag size="small" effect="plain">{{ lodgingTypeLabel(row.candidate.lodging_type) }}</el-tag>
          <span v-if="row.candidate.rating" class="ts-faint">
            {{ row.candidate.rating }} 分（{{ row.candidate.review_count ?? 0 }} 条评价）
          </span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">价格</span>
          <span class="ts-kv__v">
            {{ formatMoney(row.candidate.price_range) }}
            <el-tag v-if="!row.candidate.availability_is_realtime" size="small" type="warning" effect="plain">
              非实时库存
            </el-tag>
          </span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">地址</span>
          <span class="ts-kv__v">{{ row.candidate.address }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">通勤</span>
          <span class="ts-kv__v">{{ row.candidate.commute_summary }}</span>
        </div>
        <p class="ts-faint">
          {{ row.candidate.quality_flags.map(qualityFlagLabel).join('、') || '无质量标签' }}
          <template v-if="row.candidate.facilities.length">｜设施：{{ row.candidate.facilities.join('、') }}</template>
        </p>
      </div>
      <p v-else class="ts-faint">住宿段落引用了资源 {{ row.area }}，但当前没有该资源的候选详情。</p>
    </div>

    <div v-if="section.alternative_candidates.length > 0" class="alts">
      <p class="alts__title">备选住宿</p>
      <div v-for="item in section.alternative_candidates" :key="item.resource_id" class="alt">
        <span>{{ item.name }}</span>
        <span class="ts-faint">
          {{ lodgingTypeLabel(item.lodging_type) }}｜{{ formatMoney(item.price_range) }}｜{{ item.lodging_area }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.stay + .stay {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--ts-border);
}

.stay__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 13px;
}

.candidate {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--ts-surface-soft);
  border: 1px solid var(--ts-border);
  border-radius: 8px;
}

.candidate__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.candidate__name {
  font-size: 13px;
  font-weight: 600;
}

.candidate p {
  margin: 4px 0 0;
}

.alts {
  margin-top: 12px;
}

.alts__title {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ts-text-weak);
}

.alt {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--ts-border);
}
</style>
