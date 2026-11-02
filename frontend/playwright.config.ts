import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 35_000,
  outputDir: '../.private/verification/stage6/playwright',
  use: { baseURL: 'http://127.0.0.1:5176', channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: 'uv run --frozen python scripts/demo_ux.py', cwd: '..', url: 'http://127.0.0.1:8006/api/health', reuseExistingServer: false, timeout: 30_000 },
    { command: 'node node_modules/vite/bin/vite.js', url: 'http://127.0.0.1:5176', env: { BACKEND_PORT: '8006', FRONTEND_PORT: '5176' }, reuseExistingServer: false, timeout: 30_000 },
  ],
});
