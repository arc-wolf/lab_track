import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsStudent, ensureInventoryHasCards } from '../shared/helpers';
import { waitForPageReady, safeClick } from '../shared/ui';

test.describe('Student flow', () => {
  test('browse, add to cart, submit borrow request, view group requests', async ({ page, browser }) => {
    await ensureInventoryHasCards(page);
    await loginAsStudent(page);
    await page.goto(`${BASE_URL}/inventory/components/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.card button', { timeout: 20000 });
    const firstCard = page.locator('.card').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    await safeClick(firstCard.getByRole('button', { name: 'Add to Cart' }));
    await page.waitForSelector('a:has-text("View Cart")');

    await page.getByRole('link', { name: 'View Cart' }).click();
    await page.waitForSelector('form');

    const titleInput = page.getByPlaceholder('Enter project title');
    await expect(titleInput).toBeVisible();
    await titleInput.fill('Student Flow Project');
    await page.getByRole('button', { name: 'Generate Borrow Slip' }).click();
    await page.getByRole('button', { name: 'Confirm & Submit' }).click();
    await page.waitForSelector('table tbody tr');

    // Requests page shows the new slip
    const row = page.locator('table tbody tr').first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(/pending/i);
  });
});
