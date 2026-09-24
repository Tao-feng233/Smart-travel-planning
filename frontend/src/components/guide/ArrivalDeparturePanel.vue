<script setup lang="ts">
/**
 * 第二部分：抵达与返程。
 *
 * 城际交通只能来自数据层/MCP（红线：LLM 不是旅游事实来源），
 * 所以这里把 `source`、`evidence_ids`、`booking_advice` 一并显示，
 * 让用户看到"这个车次判断的依据是什么"。
 */
import type { ArrivalAndDepartureSection, IntercityOption } from '@/types/contract'
import { formatDateTime, formatMinutes, formatMoney, formatTimeRange } from '@/utils/format'
import { modeLabel } from '@/utils/labels'

defineProps<{ section: ArrivalAndDepartureSection }>()

function windowText(option: IntercityOption): string {
  return `${formatTimeRange(option.departure_window.start_at, option.departure_window.end_at)} 出发 → ${formatTimeRange(
    option.arrival_window.start_at,
    option.arrival_window.end_at,
  )} 到达`
}
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">二、怎么去、怎么回</h3>

    <div class="option">
      <div class="option__head">
        <el-tag size="small" type="primary" effect="light">{{ modeLabel(section.recommended_option.mode) }}</el-tag>
        <strong>{{ section.recommended_option.origin_station }} → {{ section.recommended_option.destination_station }}</strong>
        <el-tag v-if="section.recommended_option.booking_required" size="small" type="warning" effect="plain">
          需提前购票
        </el-tag>
      </div>

      <div class="ts-kv">
        <span class="ts-kv__k">时间窗</span>
        <span class="ts-kv__v">{{ windowText(section.recommended_option) }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">门到门</span>
        <span class="ts-kv__v">{{ formatMinutes(section.recommended_option.door_to_door_minutes) }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">票价</span>
        <span class="ts-kv__v">{{ formatMoney(section.recommended_option.price_range) }}</span>
      </div>
      <div class="ts-kv">
        <span class="ts-kv__k">换乘</span>
        <span class="ts-kv__v">{{ section.recommended_option.transfer_count }} 次</span>
      </div>
      <div v-if="section.recommended_option.booking_advice" class="ts-kv">
        <span class="ts-kv__k">购票建议</span>
        <span class="ts-kv__v">{{ section.recommended_option.booking_advice }}</span>
      </div>
      <p v-if="section.recommended_option.risk_flags.length > 0" class="panel__risk">
        风险：{{ section.recommended_option.risk_flags.join('；') }}
      </p>
      <p class="ts-faint">
        证据：{{ section.recommended_option.evidence_ids.join('、') || '暂无（该方案未附证据）' }}
      </p>
    </div>

    <div v-if="section.alternative_options.length > 0" class="panel__alt">
      <p class="ts-muted">备选方案</p>
      <div v-for="option in section.alternative_options" :key="option.option_id" class="alt">
        <span>{{ modeLabel(option.mode) }} {{ option.origin_station }} → {{ option.destination_station }}</span>
        <span class="ts-faint">
          {{ formatMinutes(option.door_to_door_minutes) }}｜{{ formatMoney(option.price_range) }}
        </span>
      </div>
    </div>

    <div class="panel__split">
      <div class="sub">
        <p class="sub__title">落地后怎么进城</p>
        <div class="ts-kv">
          <span class="ts-kv__k">到达站</span>
          <span class="ts-kv__v">{{ section.arrival_plan.station }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">首站</span>
          <span class="ts-kv__v">{{ section.arrival_plan.first_destination_type }} · {{ section.arrival_plan.first_destination_id }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">方式</span>
          <span class="ts-kv__v">
            {{ modeLabel(section.arrival_plan.local_transport_mode) }}｜{{ formatMinutes(section.arrival_plan.duration_minutes) }}｜{{ formatMoney(section.arrival_plan.estimated_cost) }}
          </span>
        </div>
        <p class="ts-faint">{{ section.arrival_plan.reason }}</p>
      </div>

      <div class="sub">
        <p class="sub__title">返程怎么走</p>
        <div class="ts-kv">
          <span class="ts-kv__k">出发地</span>
          <span class="ts-kv__v">{{ section.return_plan.origin_id }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">返程站</span>
          <span class="ts-kv__v">{{ section.return_plan.departure_station }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">建议离开</span>
          <span class="ts-kv__v">{{ formatDateTime(section.return_plan.recommended_leave_at) }}</span>
        </div>
        <div class="ts-kv">
          <span class="ts-kv__k">方式</span>
          <span class="ts-kv__v">
            {{ modeLabel(section.return_plan.local_transport_mode) }}｜{{ formatMinutes(section.return_plan.duration_minutes) }}｜{{ formatMoney(section.return_plan.estimated_cost) }}
          </span>
        </div>
        <p class="ts-faint">{{ section.return_plan.reason }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.option {
  padding: 10px 12px;
  background: var(--ts-surface-soft);
  border: 1px solid var(--ts-border);
  border-radius: 8px;
}

.option__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
  font-size: 13px;
}

.panel__risk {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ts-danger);
}

.panel__alt {
  margin-top: 10px;
}

.alt {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--ts-border);
}

.panel__split {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.sub {
  padding: 10px 12px;
  border: 1px dashed var(--ts-border);
  border-radius: 8px;
}

.sub__title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
}

.sub p {
  margin: 4px 0 0;
}
</style>
