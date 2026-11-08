import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
  const backendPort = Number(process.env.BACKEND_PORT || 8000);
  const frontendPort = Number(process.env.FRONTEND_PORT || 5173);
  return {
    envDir: false as const,
    plugins: [react()],
    server: {
      host: '127.0.0.1', port: frontendPort, strictPort: true,
      proxy: { '/api': `http://127.0.0.1:${backendPort}` },
    },
  };
});
