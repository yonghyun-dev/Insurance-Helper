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
  },
});
