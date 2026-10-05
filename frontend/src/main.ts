import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import zhCN from 'ant-design-vue/es/locale/zh_CN'
import 'ant-design-vue/dist/reset.css'
import 'dayjs/locale/zh-cn'

import '@/access'

const app = createApp(App)

app.use(createPinia())
app.use(router)
// 组件改为由 unplugin-vue-components 按需自动引入（见 vite.config.ts），
// 不再 app.use(Antd) 全量注册，避免把整个组件库打进首屏。

// 全局配置 Ant Design 中文语言
app.provide('locale', zhCN)

app.mount('#app')
