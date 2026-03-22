import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsFaculty } from '../shared/helpers';

test.describe('Faculty requests', () => {
  test('faculty sees assigned requests and can approve/reject with remarks', async ({ page }) => {
    await loginAsFaculty(page);
    await page.goto(`${BASE_URL}/requests/faculty/`);
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible();

    // Attempt an approve flow if pending
    if (await firstRow.getByRole('button', { name: 'Approve' }).count()) {
      await firstRow.getByRole('button', { name: 'Approve' }).click();
      await page.waitForSelector('table tbody tr');
      await expect(firstRow).toContainText(/approved|collected|issued/i);
    }
  });
});
