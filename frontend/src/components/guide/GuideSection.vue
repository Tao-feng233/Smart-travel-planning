<script setup lang="ts">
/**
 * 攻略章节的通用外壳：一张卡 + 可折叠的标题行。
 *
 * 信息分层（L1 结论 / L2 行程 / L3 证据）里，二/三/四这三段属于"要看才看"的
 * 支撑材料：默认收起，但**收起时标题行必须给出一行摘要**——
 * 用户不展开也能知道里面有什么，不必为了"有没有东西"而逐个点开。
 *
 * 为什么做成外壳而不是每块各写一遍：折叠交互、箭头方向、标题样式只维护一处，
 * 以后加新章节不用再抄一遍（前面 `DailyItineraryPanel` 是逐天折叠、语义不同，
 * 保留自己实现）。
 */
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    /** 收起时显示在标题右侧的一行摘要（没有就不显示，别硬凑） */
    summary?: string
    /** 默认是否展开。支撑材料建议 false，用户必看的建议 true */
    defaultOpen?: boolean
  }>(),
  { summary: '', defaultOpen: true },
)

const open = ref(props.defaultOpen)
</script>

<template>
  <section class="ts-card panel">
    <button
      type="button"
      class="panel__toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="panel__chevron" :class="{ 'panel__chevron--open': open }">▸</span>
      <h3 class="ts-section-title panel__title">{{ title }}</h3>
      <span v-if="!open && summary" class="ts-faint panel__summary">{{ summary }}</span>
    </button>

    <div v-show="open" class="panel__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.panel__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
  padding: 0;
  font: inherit;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
}

/* 标题的竖条高亮由 .ts-section-title::before 提供，这里只调间距 */
.panel__title {
  margin: 0;
}

.panel__chevron {
  display: inline-block;
  font-size: 11px;
  color: var(--ts-text-faint);
  transition: transform 0.15s;
}

.panel__chevron--open {
  transform: rotate(90deg);
}

.panel__summary {
  margin-left: auto;
  padding-left: 8px;
}

.panel__body {
  margin-top: 12px;
}
</style>
