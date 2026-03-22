import { test, expect, Page, Browser } from '@playwright/test';
import { ensureInventoryHasCards } from '../tests/shared/helpers';
import { waitForPageReady, safeClick } from '../tests/shared/ui';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const STUDENT_USER = process.env.STUDENT_USER || 'student01';
const STUDENT_PASS = process.env.STUDENT_PASS || 'Student@123';
const ADMIN_USER = process.env.ADMIN_USER || 'labadmin1';
const ADMIN_PASS = process.env.ADMIN_PASS || 'LabAdmin@123';
const COMPONENT_NAME = process.env.COMPONENT_NAME || ''; // optional: target component name; falls back to first available
const PROJECT_TITLE = process.env.PROJECT_TITLE || 'Playwright Borrow Flow';

async function login(page: Page, username: string, password: string) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await waitForPageReady(page);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForSelector('body');
}

async function addFirstComponentToCart(page: Page) {
  const card = COMPONENT_NAME
    ? page.getByRole('article', { name: new RegExp(COMPONENT_NAME, 'i') }).first().or(page.locator('.card').filter({ hasText: COMPONENT_NAME }).first())
    : page.locator('.card').first();

  await expect(card.getByRole('button', { name: 'Add to Cart' })).toBeVisible();
  await safeClick(card.getByRole('button', { name: 'Add to Cart' }));
  await page.waitForSelector('.toast, nav, body');
}

async function generateSlip(page: Page) {
  // Go to cart
  await Promise.all([
    page.getByRole('link', { name: 'View Cart' }).click(),
  ]);
  await page.waitForSelector('form');

  // Select first faculty option if dropdown exists
  const facultySelect = page.locator('select[name="faculty"]');
  if (await facultySelect.count()) {
    const nonEmptyOptions = await facultySelect.locator('option[value]:not([value=""])').all();
    const firstVal = await nonEmptyOptions[0]?.getAttribute('value');
    if (firstVal) {
      await facultySelect.selectOption(firstVal);
    }
  }

  await page.getByPlaceholder('Enter project title').fill(PROJECT_TITLE);
  await page.getByRole('button', { name: 'Generate Borrow Slip' }).click();
  await page.getByRole('button', { name: 'Confirm & Submit' }).click();
  await page.waitForSelector('table tbody tr');
}

async function captureLatestSlipId(page: Page) {
  const row = page.locator('table tbody tr').first();
  await expect(row).toBeVisible();
  const slipCellText = await row.getByRole('cell').first().innerText();
  return slipCellText.replace('#', '').trim();
}

async function assertSlipStatus(page: Page, slipId: string, statusText: string) {
  const row = page.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText(new RegExp(statusText, 'i'));
}

test.describe('Borrow approval flow', () => {
  test('student creates slip and admin approves it', async ({ page, browser }) => {
    test.setTimeout(60000);
    await ensureInventoryHasCards(page);
    // Student session
    await login(page, STUDENT_USER, STUDENT_PASS);
    await page.goto(`${BASE_URL}/inventory/components/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.card button:has-text("Add to Cart")', { timeout: 20000 });
    await addFirstComponentToCart(page);
    await generateSlip(page);
    await expect(page).toHaveURL(/inventory\/requests/);
    const slipId = await captureLatestSlipId(page);
    await assertSlipStatus(page, slipId, 'PENDING');

    // Admin session (separate context to avoid session bleed)
    const adminContext = await browser.newContext({ baseURL: BASE_URL });
    const adminPage = await adminContext.newPage();
    await login(adminPage, ADMIN_USER, ADMIN_PASS);
    await adminPage.goto('/requests/admin/requests/');
    await adminPage.waitForURL('**/requests/admin/requests/**');
    await adminPage.waitForSelector('input[name="q"]');
    await adminPage.locator('input[name="q"]').fill(slipId);
    await adminPage.getByRole('button', { name: 'Apply' }).click();
    await adminPage.waitForSelector('table tbody tr');

    const targetRow = adminPage.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
    await expect(targetRow).toBeVisible();
    await targetRow.getByRole('button', { name: 'Approve' }).click();
    await adminPage.waitForSelector('table tbody tr');
    await assertSlipStatus(adminPage, slipId, 'Approved');

    // Student confirms status
    await page.goto(`${BASE_URL}/inventory/requests/`);
    await assertSlipStatus(page, slipId, 'APPROVED');
  });
});
