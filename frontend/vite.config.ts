import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// 开发时把 /api 代理到后端（默认 8000）
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    rollupOptions: {
      output: {
        // 把体积大且很少变动的依赖拆成独立分块：一来首屏不必与业务代码一起
        // 重新下载，二来业务代码更新时这些分块的浏览器缓存仍然有效。
        // pdfjs 另有 lazy 包装（见 LazyAttachmentPreview），这里再兜一层，
        // 确保它不会被 rollup 合回主包。
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          antd: ['antd', '@ant-design/icons'],
          pdfjs: ['pdfjs-dist'],
        },
      },
    },
    // 分块后单块体积大幅下降，把警告阈值调回默认值以便再变大时能被发现
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
