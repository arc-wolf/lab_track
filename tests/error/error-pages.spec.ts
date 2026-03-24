import { test, expect } from '@playwright/test';
import { BASE_URL } from '../shared/helpers';

test.describe('Error handling pages', () => {
  test('403 page displays message', async ({ page }) => {
    const resp = await page.request.post(`${BASE_URL}/inventory/cart/generate/`, {
      form: { project_title: 'x' },
      failOnStatusCode: false,
    });
    expect(resp.status()).toBe(403);
    const body = await resp.text();
    expect(body).toContain('Session expired');
  });

  test('404 page shown for missing route', async ({ page }) => {
    const resp = await page.request.get(`${BASE_URL}/missing-route-xyz`, { failOnStatusCode: false });
    expect(resp.status()).toBe(404);
  });
});
