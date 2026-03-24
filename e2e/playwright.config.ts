import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  timeout: 60 * 1000,
  webServer: {
    command: "bash -lc 'if [ -x ./.venv/bin/python ]; then ./.venv/bin/python manage.py runserver 8000; elif [ -x ./venv/bin/python ]; then ./venv/bin/python manage.py runserver 8000; elif command -v python3 >/dev/null 2>&1; then python3 manage.py runserver 8000; else python manage.py runserver 8000; fi'",
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
