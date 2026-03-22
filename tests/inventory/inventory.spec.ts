import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsAdmin } from '../shared/helpers';

test.describe('Inventory UI', () => {
  test('list components and show available vs total', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`${BASE_URL}/inventory/admin/components/`);
    const row = page.locator('table tbody tr').first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(/available/i);
  });
});
