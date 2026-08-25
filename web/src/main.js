import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router/index.js'
import { initCareMode } from './lib/caremode.js'
import './styles/tokens.css'

initCareMode()

createApp(App).use(router).mount('#app')
