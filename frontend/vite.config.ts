import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
// import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // 按需自动引入 Ant Design Vue 组件，替代 main.ts 中 app.use(Antd) 的全量注册。
    // v4 采用 CSS-in-JS，样式由组件自身注入，因此 importStyle 需关闭（仅保留全局 reset.css）。
    Components({
      // 关闭 d.ts 生成：一旦生成组件类型声明，vue-tsc 就会开始校验 <a-*> 的 props，
      // 从而暴露若干与本次打包优化无关的存量类型问题并中断 npm run build。
      // 如需开启类型提示，把这里改为 'src/components.d.ts' 并修复 3 处存量报错即可。
      dts: false,
      resolvers: [
        AntDesignVueResolver({
          importStyle: false,
        }),
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    // 拆包后单文件体积上限（kB），避免正常的 vendor 分包触发体积告警
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // 把体积大、迭代频率低的第三方库拆成独立 chunk，业务代码变更时不影响其缓存。
        // 注意：这里刻意不拆 ant-design-vue —— 一旦整体固定到某个 chunk，
        // 那些只被懒加载路由用到的组件（Table / RangePicker 等）会被提升进首屏依赖，反而拖慢首屏。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('echarts') || id.includes('zrender')) return 'vendor-echarts'
          if (id.includes('/marked/')) return 'vendor-marked'
          if (id.includes('/sortablejs/')) return 'vendor-sortable'
          if (
            id.includes('vue-router') ||
            id.includes('/pinia/') ||
            id.includes('/@vue/') ||
            id.includes('/node_modules/vue/')
          ) {
            return 'vendor-vue'
          }
        },
        // 合并体积过小的碎片 chunk，减少 HTTP 请求数
        experimentalMinChunkSize: 20000,
      },
    },
  },
})
