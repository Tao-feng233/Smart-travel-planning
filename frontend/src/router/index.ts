import { createRouter, createWebHistory } from 'vue-router'

/**
 * 左侧固定是对话（`ChatPanel`），右侧两页切换：
 * - `/`      攻略（七部分）—— B6 的产物
 * - `/state` 运行状态（画像 / 候选 / 冲突 / 警告 / Trace）—— 排查与演示用，不是给游客看的
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'guide',
      component: () => import('@/views/GuideView.vue'),
      meta: { title: '行程攻略' },
    },
    {
      path: '/state',
      name: 'state',
      component: () => import('@/views/StateView.vue'),
      meta: { title: '运行状态' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
