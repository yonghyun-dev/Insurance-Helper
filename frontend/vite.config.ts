import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// @types/node 미설치 환경에서도 tsc -b 가 통과하도록 최소 ambient 선언.
declare const process: { env: Record<string, string | undefined> };

// 백엔드 프록시 타겟 — 기본 :8001. 로컬에서 다른 포트로 띄울 땐 VITE_PROXY_TARGET 로 override.
// 예) VITE_PROXY_TARGET=http://localhost:8000 npm run dev
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8001';

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
    // 교차출처/쿠키 문제 없이 동일 origin 으로 호출된다.
    proxy: {
      '/api': { target: proxyTarget, changeOrigin: true },
      '/static': { target: proxyTarget, changeOrigin: true },
    },
  },
});
