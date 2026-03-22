import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsAdmin, findSlipRow, ensureComponentExists, loginAsStudent, ensureInventoryHasCards } from '../shared/helpers';
import { waitForPageReady, safeClick } from '../shared/ui';

async function createSlip(page) {
  await ensureComponentExists(page.context().browser());
  await loginAsStudent(page);
  await ensureInventoryHasCards(page);
  await page.goto(`${BASE_URL}/inventory/components/`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.card button', { timeout: 20000 });
  const firstCard = page.locator('.card').first();
  await expect(firstCard).toBeAttached();
  await firstCard.getByRole('button', { name: 'Add to Cart' }).click();
  await page.getByRole('link', { name: 'View Cart' }).click();
  await page.waitForSelector('form');
  await page.getByPlaceholder('Enter project title').fill('Admin console slip');
  await page.getByRole('button', { name: 'Generate Borrow Slip' }).click();
  await page.getByRole('button', { name: 'Confirm & Submit' }).click();
  await page.waitForSelector('table tbody tr');
  const slipCell = await page.locator('table tbody tr').first().locator('td').first().innerText();
  return slipCell.replace('#', '').trim();
}

test.describe('Admin request console', () => {
  test('approve -> issue -> return flow on a pending slip if available', async ({ page }) => {
    const slipId = await createSlip(page);

    await loginAsAdmin(page);
    await page.goto(`${BASE_URL}/requests/admin/requests/`);
    await waitForPageReady(page);

    const row = await findSlipRow(page, slipId);

    if (await row.getByRole('button', { name: 'Approve' }).count()) {
      await safeClick(row.getByRole('button', { name: 'Approve' }));
      await page.waitForSelector('table tbody tr');
    }

    const refreshed = await findSlipRow(page, slipId);
    if (await refreshed.getByRole('button', { name: 'Mark Collected' }).count()) {
      const collector = refreshed.getByRole('textbox', { name: /Collected by/i });
      await collector.fill('Collector QA');
      await safeClick(refreshed.getByRole('button', { name: 'Mark Collected' }));
      await page.waitForSelector('table tbody tr');
    }

    const returnRow = await findSlipRow(page, slipId);
    if (await returnRow.getByRole('button', { name: 'Mark Returned' }).count()) {
      await returnRow.getByRole('button', { name: 'Mark Returned' }).click();
      const modal = page.locator('#returnModal');
      await expect(modal).toBeVisible();
      await modal.getByRole('textbox').fill('Returned OK');
      await safeClick(modal.getByRole('button', { name: 'Submit' }));
      await page.waitForSelector('table tbody tr');
    }
  });
});
