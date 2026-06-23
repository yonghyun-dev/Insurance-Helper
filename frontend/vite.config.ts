import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  css: {
    modules: {
      localsConvention: 'dashes',
      generateScopedName: '[name]_[local]__[hash:base64:5]',
    },
  },
  server: {
    port: 5173,
    host: true,
    // Sprint 20 — 백엔드(uvicorn :8001) 프록시. client.ts 가 상대경로(/api, /static)를 쓰므로
    // 교차출처/쿠키 문제 없이 동일 origin 으로 호출된다. (frontend_legacy 패턴 계승)
    proxy: {
      '/api': { target: 'http://localhost:8001', changeOrigin: true },
      '/static': { target: 'http://localhost:8001', changeOrigin: true },
    },
  },
});
