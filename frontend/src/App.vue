<script setup lang="ts">
/**
 * 应用外框：顶部品牌栏 + 全局状态条 + 左对话 / 右产出 的双栏布局。
 *
 * 为什么对话固定不跟着路由走：用户在任何时刻都需要能继续说话
 * （补信息、改行程、问冲突），把输入框藏进某个页面会让"动态行程"这个卖点断掉。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import StatusBanner from '@/components/StatusBanner.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import { useSessionStore } from '@/stores/session'
import type { RunMode } from '@/types/contract'

const store = useSessionStore()
const route = useRoute()
const router = useRouter()

const activeTab = computed({
  get: () => (route.name === 'state' ? 'state' : 'guide'),
  set: (value: string) => router.push(value === 'state' ? '/state' : '/'),
})

const runMode = ref<RunMode>('DEMO')

/**
 * 演示模式才显示开发者元素（会话 ID、fixture 演示按钮、「运行状态」页签）。
 * 真实模式面向"用户"：那些是给我们自己调试用的，与用户无关的一律收起来。
 */
const isDemo = computed(() => runMode.value === 'DEMO')

onMounted(() => {
  void store.init(runMode.value)
})

async function onRunModeChange(value: RunMode): Promise<void> {
  runMode.value = value
  // 切到真实模式时若正停在「运行状态」页，带回攻略页——那一页在真实模式下不开放
  if (value === 'VERIFIED' && route.name === 'state') {
    await router.push('/')
  }
  store.reset()
  await store.init(value)
  ElMessage.success(value === 'DEMO' ? '已切换到演示模式（数据为模拟数据）' : '已切换到真实模式')
}

async function onReset(): Promise<void> {
  try {
    await ElMessageBox.confirm('将开启一个全新的会话，当前对话与产出都会被清空。', '重新开始', {
      confirmButtonText: '重新开始',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  store.reset()
  await store.init(runMode.value)
  ElMessage.success('已开启新会话')
}

async function onFixtureDemo(): Promise<void> {
  await store.loadFixtureDemo()
  await router.push('/')
}

async function onClarifyDemo(): Promise<void> {
  await store.loadFixtureClarificationDemo()
  ElMessage.info('追问卡预览已载入（不经过后端）')
}

async function onIncompleteDemo(): Promise<void> {
  await store.loadGuideIncompleteDemo()
  await router.push('/')
  ElMessage.warning('「攻略组装不出来」状态已载入（不经过后端）')
}
</script>

<template>
  <div class="app">
    <header class="app__header">
      <div class="brand">
        <div class="brand__mark">识</div>
        <div class="brand__text">
          <h1>识途 TravelSense</h1>
          <p>AI 旅行决策与动态行程助手</p>
        </div>
      </div>

      <div class="app__header-right">
        <el-radio-group
          :model-value="runMode"
          size="small"
          @change="(value: string | number | boolean | undefined) => onRunModeChange(String(value) as RunMode)"
        >
          <el-radio-button value="DEMO">演示模式</el-radio-button>
          <el-radio-button value="VERIFIED">真实模式</el-radio-button>
        </el-radio-group>

        <template v-if="isDemo">
          <el-tag v-if="store.sessionId" size="small" type="info" effect="plain" class="ts-mono">
            {{ store.sessionId }}
          </el-tag>
          <el-tag v-else size="small" type="info" effect="plain">未连接后端</el-tag>

          <el-button v-if="store.fixtureEnabled" size="small" plain @click="onFixtureDemo">
            载入示例攻略
          </el-button>
          <el-button v-if="store.fixtureEnabled" size="small" plain @click="onClarifyDemo">
            演示追问卡
          </el-button>
          <el-button v-if="store.fixtureEnabled" size="small" plain @click="onIncompleteDemo">
            演示攻略不完整
          </el-button>
        </template>
        <el-button size="small" plain @click="onReset">重新开始</el-button>
      </div>
    </header>

    <StatusBanner />

    <div class="app__body">
      <aside class="app__left">
        <ChatPanel @goto-result="activeTab = $event" />
      </aside>

      <main class="app__right">
        <div class="app__right-head">
          <el-radio-group v-model="activeTab" size="small">
            <el-radio-button value="guide">行程攻略</el-radio-button>
            <el-radio-button v-if="isDemo" value="state">运行状态</el-radio-button>
          </el-radio-group>
          <span v-if="isDemo && store.guideOrigin === 'fixture'" class="app__badge">示例数据</span>
          <span v-else-if="isDemo && store.guideOrigin === 'api'" class="app__badge app__badge--ok">接口数据</span>
        </div>
        <div class="app__right-body">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 20px;
  background: var(--ts-surface);
  border-bottom: 1px solid var(--ts-border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand__mark {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f6803c, #ffc53d);
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand__text h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.brand__text p {
  margin: 0;
  font-size: 12px;
  color: var(--ts-text-weak);
}

.app__header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.app__body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
}

.app__left,
.app__right {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--ts-surface);
  border: 1px solid var(--ts-border);
  border-radius: var(--ts-radius);
  box-shadow: var(--ts-shadow);
  overflow: hidden;
}

.app__right-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--ts-border);
  background: var(--ts-surface-soft);
}

.app__badge {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 999px;
  color: var(--ts-warn);
  background: var(--ts-warn-soft);
  border: 1px solid #f0d9a8;
}

.app__badge--ok {
  color: #16794a;
  background: #eafaf1;
  border-color: #b7e6cd;
}

.app__right-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px;
}

@media (max-width: 1080px) {
  .app__body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(360px, 44vh) minmax(0, 1fr);
  }
}
</style>
