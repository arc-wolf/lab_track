import { test, expect, Page, Browser } from '@playwright/test';
import { ensureComponentExists, ensureInventoryHasCards } from '../tests/shared/helpers';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const STUDENT_USER = process.env.STUDENT_USER || 'student01';
const STUDENT_PASS = process.env.STUDENT_PASS || 'Student@123';
const FACULTY_USER = process.env.FACULTY_USER || 'faculty1';
const FACULTY_PASS = process.env.FACULTY_PASS || 'Faculty@123';
const ADMIN_USER = process.env.ADMIN_USER || 'labadmin1';
const ADMIN_PASS = process.env.ADMIN_PASS || 'LabAdmin@123';
const PROJECT_TITLE = process.env.PROJECT_TITLE || 'Access Control Slip';

async function login(page: Page, username: string, password: string) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await page.waitForLoadState('domcontentloaded');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForSelector('body');
}

async function createSlipAsStudent(page: Page, browser: Browser) {
  await ensureComponentExists(browser);
  await login(page, STUDENT_USER, STUDENT_PASS);
  await ensureInventoryHasCards(page);
  await page.goto(`${BASE_URL}/inventory/components/`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForSelector('.card button', { timeout: 20000 });
  // Add first available component
  const firstAddBtn = page.getByRole('button', { name: 'Add to Cart' }).first();
  await expect(firstAddBtn).toBeVisible();
  await firstAddBtn.click();
  await page.waitForSelector('a:has-text("View Cart")');

  // Go to cart and submit slip
  await page.getByRole('link', { name: 'View Cart' }).click();
  await page.waitForSelector('form');

  // Ensure project title
  await page.getByPlaceholder('Enter project title').fill(PROJECT_TITLE);
  await page.getByRole('button', { name: 'Generate Borrow Slip' }).click();
  await page.getByRole('button', { name: 'Confirm & Submit' }).click();
  await page.waitForSelector('table tbody tr');

  // Capture slip id from requests table
  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeVisible({ timeout: 10000 });
  const slipCell = await firstRow.locator('td').first().innerText();
  return slipCell.replace('#', '').trim();
}

test.describe('Role access control', () => {
  test.setTimeout(90000);

  test('student is blocked from admin console', async ({ page }) => {
    await login(page, STUDENT_USER, STUDENT_PASS);
    await page.goto(`${BASE_URL}/requests/admin/requests/`);
    await expect(page).not.toHaveURL(/\/requests\/admin\/requests\//);
  });

  test('faculty sees only assigned requests', async ({ page, browser }) => {
    // Create a slip assigned to faculty1
    const studentContext = await browser.newContext({ baseURL: BASE_URL });
    const studentPage = await studentContext.newPage();
    const slipId = await createSlipAsStudent(studentPage, browser);

    // Faculty views dashboard filtered implicitly by assignment
    await login(page, FACULTY_USER, FACULTY_PASS);
    await page.goto(`${BASE_URL}/requests/faculty/`);
    // search slip id to ensure presence
    const search = page.locator('input[name="q"]');
    if (await search.count()) {
      await search.fill(slipId);
      const applyBtn = page.getByRole('button', { name: /Apply/i });
      if (await applyBtn.count()) {
      await applyBtn.click();
      await page.waitForSelector('table tbody tr');
      }
    }
    const row = page.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
    await expect(row).toBeAttached({ timeout: 10000 });
    await expect(row).toContainText(/pending/i);
  });

  test('admin sees full control panel', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
  await page.goto(`${BASE_URL}/requests/admin/requests/`);
  await page.waitForLoadState('domcontentloaded');
  const heading = page.locator('h1', { hasText: 'Borrow Request Lifecycle' }).or(page.getByText('Borrow Request Lifecycle', { exact: true }));
  await expect(heading).toBeVisible({ timeout: 20000 });
  const firstRow = page.locator('table tbody tr').first();
  await expect(firstRow).toBeAttached({ timeout: 10000 });
  });
});
