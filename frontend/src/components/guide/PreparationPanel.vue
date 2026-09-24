<script setup lang="ts">
/** 第三部分：行前准备。`priority` 决定视觉权重，`due_at` 是提醒时间而不是截止时间。 */
import { computed } from 'vue'

import type { PreparationItem, PreparationSection } from '@/types/contract'
import { formatDateTime } from '@/utils/format'
import { prepCategoryLabel, prepPriorityLabel } from '@/utils/labels'

const props = defineProps<{ section: PreparationSection }>()

const groups = computed(() => {
  const map = new Map<string, PreparationItem[]>()
  for (const item of props.section.items) {
    const list = map.get(item.category) ?? []
    list.push(item)
    map.set(item.category, list)
  }
  return [...map.entries()].map(([category, items]) => ({ category, items }))
})

function priorityType(priority: PreparationItem['priority']): 'danger' | 'warning' | 'info' {
  if (priority === 'REQUIRED') return 'danger'
  if (priority === 'RECOMMENDED') return 'warning'
  return 'info'
}
</script>

<template>
  <section class="ts-card panel">
    <h3 class="ts-section-title">三、行前准备</h3>

    <div v-if="section.items.length === 0" class="ts-faint">暂无准备事项。</div>

    <div v-for="group in groups" :key="group.category" class="group">
      <p class="group__name">{{ prepCategoryLabel(group.category) }}</p>
      <ul class="items">
        <li v-for="item in group.items" :key="item.item_id" class="item">
          <div class="item__head">
            <span class="item__title">{{ item.title }}</span>
            <el-tag size="small" :type="priorityType(item.priority)" effect="plain">
              {{ prepPriorityLabel(item.priority) }}
            </el-tag>
            <span v-if="item.due_at" class="ts-faint">提前到 {{ formatDateTime(item.due_at) }}</span>
          </div>
          <p class="item__desc">{{ item.description }}</p>
          <p class="ts-faint">原因：{{ item.reason }}</p>
        </li>
      </ul>
    </div>

    <div v-if="section.refresh_before_departure.length > 0" class="refresh">
      <p class="group__name">出发前需要重新核对</p>
      <ul class="items">
        <li v-for="item in section.refresh_before_departure" :key="item.item_id" class="item">
          <div class="item__head">
            <span class="item__title">{{ item.title }}</span>
            <span v-if="item.due_at" class="ts-faint">{{ formatDateTime(item.due_at) }}</span>
          </div>
          <p class="item__desc">{{ item.description }}</p>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.group + .group,
.refresh {
  margin-top: 10px;
}

.group__name {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ts-text-weak);
}

.items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  padding: 6px 0;
  border-bottom: 1px dashed var(--ts-border);
}

.item:last-child {
  border-bottom: none;
}

.item__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.item__title {
  font-size: 13px;
  font-weight: 500;
}

.item__desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.item p {
  margin: 2px 0 0;
}
</style>
