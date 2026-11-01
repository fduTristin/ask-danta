import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('..', import.meta.url));
  const env = loadEnv(mode, root, ['BACKEND_PORT', 'FRONTEND_PORT']);
  const backendPort = Number(process.env.BACKEND_PORT || env.BACKEND_PORT || 8000);
  const frontendPort = Number(process.env.FRONTEND_PORT || env.FRONTEND_PORT || 5173);
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1', port: frontendPort, strictPort: true,
      proxy: { '/api': `http://127.0.0.1:${backendPort}` },
    },
  };
});
