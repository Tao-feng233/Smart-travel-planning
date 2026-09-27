<script setup lang="ts">
/**
 * 「本轮改动」：`GuideChangeData` 的两个附加产物。
 *
 * 为什么要单独一块展示：
 * 1. `version_lineage` 是重规划后**唯一**能回答"我原来安排的什么被换掉了"的东西。
 *    只给新版本号，用户没法判断这次改动动到了哪里——尤其"报突发"之后。
 * 2. `conflicts` 是**还没解决**的问题（严重度 / 范围 / 可选的修法）。
 *    它不属于 warning（warning 是数据来源类提示），必须单独露出，
 *    否则用户会以为这份攻略是干净的。
 *
 * 谱系里只有 `node_id`，要摊开给用户看必须回到攻略正文里查名字。
 * 而 `removed_node_ids` / `replacement_relations.old_node_id` 是**旧版**节点，
 * 在新版正文里查不到，旧版也取不回来（`GET /api/guides/{id}?version=N` 实测 404，
 * 根因是 `store_guide` 按 `guide_id` 覆盖、同 ID 只留最新版），
 * 所以调用方要把"改动前那一版"一起传进来当索引。
 * 两版都查不到名字就原样回显 ID 并标注，绝不编一个名字出来。
 */
import { computed } from 'vue'

import type { Conflict, TravelGuide, VersionLineage } from '@/types/contract'
import { severityLabel } from '@/utils/labels'

const props = defineProps<{
  guide: TravelGuide
  /** 产出这份谱系的**改动前**那一版攻略，用来解析被移除/被替换的旧节点名。 */
  previousGuide: TravelGuide | null
  lineage: VersionLineage | null
  conflicts: Conflict[]
}>()

/** node_id → 节点名称。新版优先，旧版兜住被移除/被替换的那些。 */
const nodeNames = computed(() => {
  const map = new Map<string, string>()
  for (const source of [props.previousGuide, props.guide]) {
    for (const day of source?.daily_itinerary ?? []) {
      for (const node of day.nodes) map.set(node.node_id, node.name)
    }
  }
  return map
})

function nameOf(nodeId: string): string {
  return nodeNames.value.get(nodeId) ?? nodeId
}

/** 两版正文里都找不到这个名字——要如实标出来，不能让裸 ID 冒充节点名。 */
function unresolved(nodeId: string): boolean {
  return !nodeNames.value.has(nodeId)
}

/** 谱系的三类节点分栏。写成数据而不是三段模板，免得三处各改一遍。 */
const buckets = computed(() => {
  const lineage = props.lineage
  if (!lineage) return []
  return [
    {
      key: 'preserved',
      label: '保留',
      tagType: 'success' as const,
      emptyText: '没有节点被保留',
      nodeIds: lineage.preserved_node_ids,
    },
    {
      key: 'changed',
      label: '替换',
      tagType: 'warning' as const,
      emptyText: '没有节点被替换',
      nodeIds: lineage.changed_node_ids,
    },
    {
      key: 'removed',
      label: '移除',
      tagType: 'info' as const,
      emptyText: '没有节点被移除',
      nodeIds: lineage.removed_node_ids,
    },
  ]
})

/** 版本号是可空字段：缺就宁可不显示，也不要拿 0 或当前版本凑数。 */
function versionStep(from: number | null, to: number | null): string | null {
  if (from === null || to === null) return null
  return `v${from} → v${to}`
}

const planStep = computed(() =>
  versionStep(props.lineage?.parent_plan_version ?? null, props.lineage?.new_plan_version ?? null),
)
const guideStep = computed(() =>
  versionStep(props.lineage?.parent_guide_version ?? null, props.lineage?.new_guide_version ?? null),
)
</script>

<template>
  <section v-if="lineage || conflicts.length > 0" class="ts-card panel">
    <h3 class="ts-section-title">本轮改动</h3>

    <template v-if="lineage">
      <p class="ts-faint panel__meta">
        改动单 <span class="ts-mono">{{ lineage.change_request_id }}</span>
        <template v-if="planStep">｜计划 {{ planStep }}</template>
        <template v-if="guideStep">｜攻略 {{ guideStep }}</template>
        <template v-else>｜当前攻略 v{{ guide.guide_version }}（谱系未带攻略版本号）</template>
      </p>

      <div class="panel__grid">
        <div v-for="bucket in buckets" :key="bucket.key" class="bucket">
          <span class="bucket__k">{{ bucket.label }} {{ bucket.nodeIds.length }} 个</span>
          <div class="bucket__tags">
            <el-tag
              v-for="nodeId in bucket.nodeIds"
              :key="nodeId"
              size="small"
              :type="bucket.tagType"
              effect="plain"
            >
              {{ nameOf(nodeId) }}
              <span v-if="unresolved(nodeId)" class="tag__note">（名称不可得）</span>
            </el-tag>
            <span v-if="bucket.nodeIds.length === 0" class="ts-faint">{{ bucket.emptyText }}</span>
          </div>
        </div>
      </div>

      <ul v-if="lineage.replacement_relations.length > 0" class="relations">
        <li
          v-for="rel in lineage.replacement_relations"
          :key="`${rel.old_node_id}->${rel.new_node_id}`"
        >
          <span class="relations__old">{{ nameOf(rel.old_node_id) }}</span>
          <span class="relations__arrow">→</span>
          <span class="relations__new">{{ nameOf(rel.new_node_id) }}</span>
        </li>
      </ul>
    </template>

    <div v-if="conflicts.length > 0" class="conflicts">
      <p class="conflicts__title ts-muted">还没解决的问题（{{ conflicts.length }}）</p>
      <el-alert
        v-for="conflict in conflicts"
        :key="conflict.conflict_id"
        class="conflict"
        :type="conflict.severity === 'ERROR' ? 'error' : 'warning'"
        :closable="false"
        show-icon
        :title="conflict.message"
        :description="`严重度：${severityLabel(conflict.severity)}｜范围：${conflict.scope}｜受影响节点 ${conflict.affected_node_ids.length} 个｜可选修法 ${conflict.repair_options.length} 个`"
      />
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 14px;
}

.panel__meta {
  margin: 6px 0 10px;
  font-size: 12px;
}

.panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 18px;
}

.bucket__k {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.bucket__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

.tag__note {
  color: var(--ts-text-faint);
}

.relations {
  margin: 12px 0 0;
  padding-left: 18px;
  font-size: 13px;
}

.relations__old {
  color: var(--ts-text-faint);
  text-decoration: line-through;
}

.relations__arrow {
  margin: 0 6px;
  color: var(--ts-text-faint);
}

.relations__new {
  font-weight: 600;
}

.conflicts {
  margin-top: 12px;
}

.conflicts__title {
  margin: 0 0 6px;
  font-size: 13px;
}

.conflict + .conflict {
  margin-top: 8px;
}
</style>
