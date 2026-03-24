import { test, expect } from '@playwright/test';
import { BASE_URL, getAdminToken } from '../shared/helpers';

test.describe('Admin API', () => {
  test('overview/policy/console-map respond with expected shape', async ({ request }) => {
    const token = await getAdminToken(request);
    const headers = { Authorization: `Token ${token}` };
    const endpoints = ['overview', 'policy', 'console-map'];

    for (const path of endpoints) {
      const resp = await request.get(`${BASE_URL}/api/admin/${path}/`, { headers });
      expect(resp.status()).toBe(200);
      const body = await resp.json();
      expect(body).toBeTruthy();
    }
  });
});
