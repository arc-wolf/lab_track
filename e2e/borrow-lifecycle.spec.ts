import { test, expect, Browser, Page } from '@playwright/test';
import { ensureComponentExists, ensureInventoryHasCards } from '../tests/shared/helpers';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const STUDENT_USER = process.env.STUDENT_USER || 'student01';
const STUDENT_PASS = process.env.STUDENT_PASS || 'Student@123';
const ADMIN_USER = process.env.ADMIN_USER || 'labadmin1';
const ADMIN_PASS = process.env.ADMIN_PASS || 'LabAdmin@123';
const FACULTY_USER = process.env.FACULTY_USER || 'faculty1';
const FACULTY_PASS = process.env.FACULTY_PASS || 'Faculty@123';
const PROJECT_TITLE = process.env.PROJECT_TITLE || 'E2E Borrow Lifecycle';
const COLLECTOR_NAME = process.env.COLLECTOR_NAME || 'Collector Bot';

async function login(page: Page, username: string, password: string) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('input[name="username"]')).toBeVisible();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForSelector('body');
}

async function createSlipAsStudent(page: Page): Promise<string> {
  await login(page, STUDENT_USER, STUDENT_PASS);
  await ensureInventoryHasCards(page);
  await page.goto(`${BASE_URL}/inventory/components/`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForSelector('.card button', { timeout: 20000 });

  const firstCard = page.locator('.card').first();
  await expect(firstCard).toBeAttached();
  await firstCard.getByRole('button', { name: 'Add to Cart' }).click();
  await page.waitForSelector('a:has-text("View Cart")');

  await page.getByRole('link', { name: 'View Cart' }).click();
  await page.waitForSelector('form');

  // Fill project title and submit
  await expect(page.getByPlaceholder('Enter project title')).toBeVisible();
  await page.getByPlaceholder('Enter project title').fill(PROJECT_TITLE);
  await page.getByRole('button', { name: 'Generate Borrow Slip' }).click();
  await page.getByRole('button', { name: 'Confirm & Submit' }).click();
  await page.waitForSelector('table tbody tr');

  // Capture slip id
  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeVisible();
  const slipCell = await firstRow.getByRole('cell').first().innerText();
  return slipCell.replace('#', '').trim();
}

async function findSlipRow(page: Page, slipId: string) {
  await page.locator('input[name="q"], input[type="search"]').fill(slipId);
  await page.getByRole('button', { name: 'Apply' }).click();
  await page.waitForSelector('table tbody tr');
  const row = page.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
  await expect(row).toBeVisible();
  return row;
}

test.describe('Borrow lifecycle across roles', () => {
  test.setTimeout(120000);

  test('full lifecycle: student creates, admin approves/issues/returns', async ({ page, browser }) => {
    await ensureComponentExists(browser);
    // Create slip as student
    const studentContext = await browser.newContext({ baseURL: BASE_URL });
    const studentPage = await studentContext.newPage();
    const slipId = await createSlipAsStudent(studentPage);
    await studentContext.close();

    // Admin approves
  await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto(`${BASE_URL}/requests/admin/requests/`);
  await page.waitForURL(/requests\/admin\/requests/);
  let row = await findSlipRow(page, slipId);
  await expect(row).toContainText(/pending/i);
  await row.getByRole('button', { name: 'Approve' }).click();
  await page.waitForSelector('table tbody tr');

    // Admin marks issued
    row = await findSlipRow(page, slipId);
  await expect(row).toContainText(/approved/i);
  const collectorInput = row.getByRole('textbox', { name: /Collected by/i });
  await expect(collectorInput).toBeVisible();
  await collectorInput.fill(COLLECTOR_NAME);
  await row.getByRole('button', { name: 'Mark Collected' }).click();
  await page.waitForSelector('table tbody tr');

    // Admin marks returned
    row = await findSlipRow(page, slipId);
    const returnBtn = row.getByRole('button', { name: 'Mark Returned' });
    await expect(returnBtn).toBeVisible();
    await returnBtn.click();
  const modal = page.locator('#returnModal');
  await expect(modal).toBeVisible();
  await modal.getByRole('textbox').fill('Returned in good condition');
  await modal.getByRole('button', { name: 'Submit' }).click();
  await page.waitForSelector('table tbody tr');

    // Verify student sees returned
    const studentVerifyCtx = await browser.newContext({ baseURL: BASE_URL });
    const studentVerifyPage = await studentVerifyCtx.newPage();
    await login(studentVerifyPage, STUDENT_USER, STUDENT_PASS);
    await studentVerifyPage.goto(`${BASE_URL}/inventory/requests/`);
    const studentRow = studentVerifyPage.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
    await expect(studentRow).toBeVisible();
    await expect(studentRow).toContainText(/returned/i);
    await studentVerifyCtx.close();
  });

  test('role restrictions: student cannot access admin console', async ({ page }) => {
    await login(page, STUDENT_USER, STUDENT_PASS);
    await page.goto(`${BASE_URL}/requests/admin/requests/`);
    await expect(page).not.toHaveURL(/requests\/admin\/requests/);
  });

  test('faculty sees only assigned requests', async ({ page, browser }) => {
    await ensureComponentExists(browser);
    // Create slip with pre-assigned faculty1 via group data
    const studentContext = await browser.newContext({ baseURL: BASE_URL });
    const studentPage = await studentContext.newPage();
    const slipId = await createSlipAsStudent(studentPage);
    await studentContext.close();

  await login(page, FACULTY_USER, FACULTY_PASS);
  await page.goto(`${BASE_URL}/requests/faculty/`);
  await page.waitForURL(/requests\/faculty/);
  await page.waitForSelector('table', { timeout: 20000 });
    await page.locator('input[name="q"], input[type="search"]').fill(slipId);
    await page.getByRole('button', { name: 'Apply' }).click();
    await page.waitForSelector('table tbody tr');
    const row = page.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
    await expect(row).toBeAttached();
    await expect(row).toContainText(/pending/i);
  });
});
