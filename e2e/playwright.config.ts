import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  timeout: 60 * 1000,
  webServer: {
    command: './venv/bin/python manage.py runserver 8000',
    url: 'http://localhost:8000',
    reuseExistingServer: true,
    timeout: 120000,
  },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    headless: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
