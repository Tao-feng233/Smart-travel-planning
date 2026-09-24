<script setup lang="ts">
/**
 * 第五部分：每日行程 —— 攻略的主体。
 *
 * 关键点：节点（`GuideNode`）与出行段（`TravelLeg`）按时间**交错**展示。
 * 契约把普通交通放在 `travel_legs` 里、不建 `TRANSFER` 节点，
 * 所以前端必须自己把两者按时序合并，否则用户会看到"突然出现在另一个地方"。
 *
 * 时间排序用字符串前 19 位（`YYYY-MM-DDTHH:MM:SS`）比较，
 * 不经过 `new Date()`，避免时区平移导致顺序错乱。
 */
import { computed } from 'vue'

import type { GuideDay, GuideNode, TravelLeg } from '@/types/contract'
import { formatMinutes, formatMoney, formatTime, formatTimeRange } from '@/utils/format'
import {
  intensityLabel,
  legSourceLabel,
  modeLabel,
  nodeTypeLabel,
  walkingBurdenLabel,
} from '@/utils/labels'

const props = defineProps<{ days: GuideDay[] }>()

type TimelineItem =
  | { kind: 'node'; key: string; at: string; node: GuideNode }
  | { kind: 'leg'; key: string; at: string; leg: TravelLeg }

interface DayRow {
  day: GuideDay
  timeline: TimelineItem[]
  nodeNames: Record<string, string>
}

function sortKey(value: string): string {
  return value.slice(0, 19)
}

const rows = computed<DayRow[]>(() =>
  props.days.map((day) => {
    const timeline: TimelineItem[] = [
      ...day.nodes.map<TimelineItem>((node) => ({ kind: 'node', key: node.node_id, at: node.start_at, node })),
      ...day.travel_legs.map<TimelineItem>((leg) => ({ kind: 'leg', key: leg.leg_id, at: leg.depart_at, leg })),
    ].sort((a, b) => sortKey(a.at).localeCompare(sortKey(b.at)))

    // 出行段只给节点 ID，名称要从当天的节点表里查；查不到就显示 ID，不编造
    const nodeNames: Record<string, string> = {}
    for (const node of day.nodes) {
      nodeNames[node.node_id] = node.name
    }

    return { day, timeline, nodeNames }
  }),
)

function nodeTone(node: GuideNode): 'primary' | 'success' | 'warning' | 'info' {
  if (node.node_type === 'MEAL') return 'warning'
  if (node.node_type === 'ATTRACTION') return 'primary'
  if (node.node_type === 'LODGING' || node.node_type === 'CHECK_IN') return 'success'
  return 'info'
}
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">五、每天怎么走</h3>

    <div v-if="rows.length === 0" class="ts-faint">还没有每日行程。</div>

    <article v-for="row in rows" :key="row.day.date" class="day">
      <header class="day__head">
        <div class="day__title">
          <span class="day__date">{{ row.day.date.slice(5) }}</span>
          <strong>{{ row.day.day_theme }}</strong>
          <el-tag size="small" effect="plain">{{ intensityLabel(row.day.intensity_level) }}</el-tag>
        </div>
        <div class="day__stats">
          <span>活动 {{ formatMinutes(row.day.total_activity_minutes) }}</span>
          <span>交通 {{ formatMinutes(row.day.total_travel_minutes) }}</span>
          <span class="day__cost">约 {{ formatMoney(row.day.estimated_cost) }}</span>
        </div>
      </header>

      <p class="ts-faint day__areas">
        活动区域：{{ row.day.activity_areas.join('、') || '—' }}｜
        {{ row.day.start_location }} → {{ row.day.end_location }}
      </p>

      <el-alert
        v-for="warning in row.day.warnings"
        :key="warning"
        class="day__warning"
        type="warning"
        :closable="false"
        show-icon
        :title="warning"
      />

      <div class="timeline">
        <div v-for="item in row.timeline" :key="item.key" class="tl-item">
          <div class="tl-time">{{ formatTime(item.at) }}</div>
          <div class="tl-line">
            <span class="tl-dot" :class="`tl-dot--${item.kind}`"></span>
          </div>

          <!-- 出行段 -->
          <div v-if="item.kind === 'leg'" class="leg">
            <span class="leg__mode">{{ modeLabel(item.leg.recommended_mode) }}</span>
            <span class="ts-faint">
              {{ row.nodeNames[item.leg.from_node_id] ?? item.leg.from_node_id }} →
              {{ row.nodeNames[item.leg.to_node_id] ?? item.leg.to_node_id }}
            </span>
            <span class="ts-faint">
              {{ formatMinutes(item.leg.duration_minutes) }}｜{{ item.leg.distance_km }} km｜换乘
              {{ item.leg.transfer_count }} 次｜{{ walkingBurdenLabel(item.leg.walking_burden) }}
            </span>
            <el-tag v-if="item.leg.alternative_modes.length" size="small" effect="plain">
              备选 {{ item.leg.alternative_modes.map(modeLabel).join('/') }}
            </el-tag>
            <el-tag v-if="item.leg.source === 'FAKE'" size="small" type="warning" effect="plain">
              {{ legSourceLabel(item.leg.source) }}
            </el-tag>
            <p class="leg__reason ts-faint">{{ item.leg.reason }}</p>
            <p v-if="item.leg.congestion_note" class="ts-faint">拥堵提示：{{ item.leg.congestion_note }}</p>
          </div>

          <!-- 节点 -->
          <div v-else class="node">
            <div class="node__head">
              <el-tag size="small" :type="nodeTone(item.node)" effect="light">
                {{ nodeTypeLabel(item.node.node_type) }}
              </el-tag>
              <span class="node__name">{{ item.node.name }}</span>
              <el-tag v-if="item.node.locked" size="small" type="info" effect="plain">已锁定</el-tag>
              <el-tag v-if="item.node.reservation_required" size="small" type="warning" effect="plain">需预约</el-tag>
            </div>
            <p class="ts-faint node__time">
              {{ formatTimeRange(item.node.start_at, item.node.end_at) }}
              <template v-if="item.node.address">｜{{ item.node.address }}</template>
              ｜{{ formatMoney(item.node.estimated_cost) }}
            </p>
            <p v-if="item.node.opening_window" class="ts-faint">
              开放 {{ formatTime(item.node.opening_window.start_at) }}-{{ formatTime(item.node.opening_window.end_at) }}
              <template v-if="item.node.last_entry_at">｜最晚入场 {{ formatTime(item.node.last_entry_at) }}</template>
            </p>
            <p class="node__reason">{{ item.node.reason }}</p>
            <ul v-if="item.node.tips.length" class="node__tips">
              <li v-for="tip in item.node.tips" :key="tip">{{ tip }}</li>
            </ul>
          </div>
        </div>
      </div>

      <p v-if="row.day.alternative_plan_ids.length > 0" class="ts-faint day__alts">
        这天有 {{ row.day.alternative_plan_ids.length }} 个备选方案：{{ row.day.alternative_plan_ids.join('、') }}
      </p>
    </article>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.day + .day {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--ts-border);
}

.day__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.day__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.day__date {
  font-weight: 700;
  color: var(--ts-brand);
}

.day__stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.day__cost {
  font-weight: 600;
  color: var(--ts-text);
}

.day__areas {
  margin: 4px 0 8px;
}

.day__warning {
  margin-bottom: 6px;
}

.timeline {
  display: flex;
  flex-direction: column;
}

.tl-item {
  display: grid;
  grid-template-columns: 44px 14px minmax(0, 1fr);
  gap: 6px;
  align-items: stretch;
}

.tl-time {
  padding-top: 6px;
  font-size: 12px;
  color: var(--ts-text-weak);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.tl-line {
  position: relative;
  display: flex;
  justify-content: center;
}

.tl-line::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--ts-border);
}

.tl-item:first-child .tl-line::before {
  top: 12px;
}

.tl-item:last-child .tl-line::before {
  bottom: auto;
  height: 12px;
}

.tl-dot {
  position: relative;
  margin-top: 9px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ts-brand);
  box-shadow: 0 0 0 3px #fff;
}

.tl-dot--leg {
  background: #b8c0cc;
  width: 6px;
  height: 6px;
}

.node,
.leg {
  padding: 4px 0 10px;
}

.node__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.node__name {
  font-size: 13px;
  font-weight: 600;
}

.node__time {
  margin: 2px 0 0;
}

.node__reason {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.node__tips {
  margin: 3px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.leg {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.leg__mode {
  font-weight: 600;
}

.leg__reason {
  flex-basis: 100%;
  margin: 0;
}

.day__alts {
  margin: 4px 0 0;
}
</style>
