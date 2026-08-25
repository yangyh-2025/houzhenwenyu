import { createApp } from 'vue'
import App from './App.vue'
import { preloadAudio } from './lib/tts.js'
import { router } from './router/index.js'
import { initCareMode } from './lib/caremode.js'
import './styles/tokens.css'

initCareMode()

createApp(App).use(router).mount('#app')

// 启动即预加载全部音频（零延迟交互）
preloadAudio()
