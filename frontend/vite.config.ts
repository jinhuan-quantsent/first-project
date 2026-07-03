import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  build: {
    // 目标现代浏览器，启用更激进的优化
    target: 'es2020',
    // esbuild minify（Vite 内置，无需额外安装）
    minify: 'esbuild',
    // 分包策略
    rollupOptions: {
      output: {
        // 手动分包：echarts 独立 chunk，利用浏览器缓存
        manualChunks: {
          // ECharts 核心 + 按需加载的组件 → 独立 vendor chunk
          'vendor-echarts': [
            'echarts/core',
            'echarts/charts',
            'echarts/components',
            'echarts/renderers',
            'echarts-for-react/lib/core',
          ],
          // React 生态独立 chunk
          'vendor-react': [
            'react',
            'react-dom',
            'react-router-dom',
          ],
          // UI 工具库
          'vendor-ui': [
            'lucide-react',
            'zustand',
            'clsx',
            'tailwind-merge',
          ],
        },
      },
    },
    // chunk 大小警告阈值
    chunkSizeWarningLimit: 600,
  },
});
