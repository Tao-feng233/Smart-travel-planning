import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const repoRoot = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 直接读仓库根目录的契约样例，避免在前端复制一份模拟数据
      '@fixtures': fileURLToPath(new URL('../fixtures', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 允许开发服务器读取仓库根目录（fixtures 在上面一层）
    fs: { allow: [repoRoot] },
    proxy: {
      // 后端 FastAPI（uvicorn app.main:app）默认端口
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
