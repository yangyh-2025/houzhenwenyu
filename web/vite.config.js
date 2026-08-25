import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 患者端 H5 构建目标 es2018（微信 XWeb 内核 Chromium 78+ 基线），
// 禁用 :has() 等新潮 CSS；布局 rem/clamp/vw 适配微信关怀模式放大。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    target: 'es2018',
  },
  server: {
    // 本地开发时将 /api 反代到 FastAPI（uvicorn 127.0.0.1:8000）
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
