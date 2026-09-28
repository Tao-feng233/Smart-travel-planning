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
 * **这两个产物都不能挂在"有没有攻略"下面**：首次规划就卡在 `REPAIRING` 时，
 * 后端已经带回了 `conflicts`，但那时**还没有攻略**（`data.guide_id` 为空）。
 * 所以本组件允许 `guide` 为空，由调用方在"有计划、没攻略"时也挂出来。
 *
 * 谱系里只有 `node_id`，要摊开给用户看必须回到攻略正文里查名字。
 * `removed_node_ids` / `replacement_relations.old_node_id` 是**旧版**节点，
 * 在新版正文里查不到，所以调用方把"改动前那一版"一起传进来当索引。
 * 两版都查不到名字就原样回显 ID 并标注，绝不编一个名字出来。
 * （历史版本本身现在可以从后端取回了 —— C 已把 `store_guide` 改成按
 * `(guide_id, guide_version)` 保留全部版本，`?version=N` 不再是死参数。
 * 这里仍用调用方手里的那一版，是为了少一次请求，不是因为取不到。）
 */
import { computed } from 'vue'

import type { Conflict, TravelGuide, VersionLineage } from '@/types/contract'
import { severityLabel } from '@/utils/labels'

const props = defineProps<{
  /** 当前攻略；**首次规划卡在 `REPAIRING` 时为空**（此时只有 conflicts，没有正文）。 */
  guide: TravelGuide | null
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

/** 没有谱系时这块只剩 conflicts，标题就别再说「本轮改动」了。 */
const panelTitle = computed(() => (props.lineage ? '本轮改动' : '需要你处理的冲突'))

const conflictsTitle = computed(() =>
  props.lineage ? `还没解决的问题（${props.conflicts.length}）` : `共 ${props.conflicts.length} 个`,
)

/** 冲突的元信息。修法单独列在下面，不塞进这一行里挤成一团。 */
function conflictMeta(conflict: Conflict): string {
  return `严重度：${severityLabel(conflict.severity)}｜范围：${conflict.scope}｜受影响节点 ${conflict.affected_node_ids.length} 个`
}
</script>

<template>
  <section v-if="lineage || conflicts.length > 0" class="ts-card panel">
    <h3 class="ts-section-title">{{ panelTitle }}</h3>

    <template v-if="lineage">
      <p class="ts-faint panel__meta">
        改动单 <span class="ts-mono">{{ lineage.change_request_id }}</span>
        <template v-if="planStep">｜计划 {{ planStep }}</template>
        <template v-if="guideStep">｜攻略 {{ guideStep }}</template>
        <template v-else-if="guide">｜当前攻略 v{{ guide.guide_version }}（谱系未带攻略版本号）</template>
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
      <p class="conflicts__title ts-muted">{{ conflictsTitle }}</p>
      <div v-for="conflict in conflicts" :key="conflict.conflict_id" class="conflict">
        <el-alert
          :type="conflict.severity === 'ERROR' ? 'error' : 'warning'"
          :closable="false"
          show-icon
          :title="conflict.message"
          :description="conflictMeta(conflict)"
        />
        <!-- 只**列出**可选修法，不在这里发起修改：改哪一条、要不要确认
             是用户的选择，走哪个入口由页面定，组件不替用户下决定。 -->
        <ul v-if="conflict.repair_options.length > 0" class="options">
          <li v-for="option in conflict.repair_options" :key="option.repair_option_id">
            <span>{{ option.description }}</span>
            <el-tag
              v-if="option.requires_user_confirmation"
              size="small"
              type="warning"
              effect="plain"
            >
              需你确认
            </el-tag>
          </li>
        </ul>
      </div>
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
  margin-top: 10px;
}

.options {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.options li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 0;
}
</style>
