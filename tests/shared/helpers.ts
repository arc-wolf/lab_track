import { expect, Page, APIRequestContext, Browser } from '@playwright/test';
import fs from 'fs';
import path from 'path';

export const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
export const STUDENT_USER = process.env.STUDENT_USER || 'student01';
export const STUDENT_PASS = process.env.STUDENT_PASS || 'Student@123';
export const FACULTY_USER = process.env.FACULTY_USER || 'faculty1';
export const FACULTY_PASS = process.env.FACULTY_PASS || 'Faculty@123';
export const ADMIN_USER = process.env.ADMIN_USER || 'labadmin1';
export const ADMIN_PASS = process.env.ADMIN_PASSWORD || process.env.ADMIN_PASS || 'LabAdmin@123';
let componentCounter = Date.now();
const STATE_DIR = path.join(__dirname, '..', '..', '.playwright-state');
const CSV_SEED = 'name,category,total_stock\nPXAuto,Auto,5';

export async function login(page: Page, username: string, password: string) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('input[name="username"]')).toBeVisible({ timeout: 15000 });
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForSelector('body', { state: 'attached', timeout: 15000 });
}

export const loginAsStudent = (page: Page) => login(page, STUDENT_USER, STUDENT_PASS);
export const loginAsFaculty = (page: Page) => login(page, FACULTY_USER, FACULTY_PASS);
export const loginAsAdmin = (page: Page) => login(page, ADMIN_USER, ADMIN_PASS);

export async function getAdminToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${BASE_URL}/api/auth/token/`, {
    data: { identity: ADMIN_USER, password: ADMIN_PASS },
  });
  expect(resp.ok()).toBeTruthy();
  return (await resp.json()).token;
}

export async function findSlipRow(page: Page, slipId: string) {
  const searchBox = page.locator('input[name="q"], input[type="search"]');
  if (await searchBox.count()) {
    await searchBox.fill(slipId);
    if (await page.getByRole('button', { name: /Apply/i }).count()) {
      await page.getByRole('button', { name: /Apply/i }).click();
      await page.waitForTimeout(200);
    }
  }
  const row = page.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
  await expect(row).toBeAttached();
  return row;
}

export async function ensureComponentExists(browser, namePrefix = 'E2EComp'): Promise<string> {
  const name = `${namePrefix}-${componentCounter++}`;
  const context = await browser.newContext({ baseURL: BASE_URL });
  const page = await context.newPage();
  await loginAsAdmin(page);
  await page.goto(`${BASE_URL}/inventory/admin/components/new/`);
  await expect(page.getByLabel(/Name/i)).toBeVisible({ timeout: 10000 });
  await page.getByLabel(/Name/i).fill(name);
  await page.getByLabel(/Category/i).fill('TestCat');
  await page.getByLabel(/Total stock/i).fill('10');
  await page.getByLabel(/Available stock/i).fill('10');
  await page.getByRole('button', { name: /Save|Add|Submit|Create/i }).click();
  await page.waitForSelector('body');
  await context.close();
  return name;
}

export async function ensureComponentViaApi(page: Page) {
  const authed = await authedRequestFromPage(page);
  await authed.post(`${BASE_URL}/inventory/import-excel/`, {
    multipart: { file: { name: 'seed.csv', buffer: Buffer.from(CSV_SEED), mimeType: 'text/csv' } },
  });
}

export async function ensureInventoryHasCards(page: Page) {
  // Seed inventory only; callers should handle their own navigation/login flow.
  const seedContext = await page.context().browser()?.newContext({ baseURL: BASE_URL });
  const seedPage = await seedContext?.newPage();
  if (seedPage) {
    await login(seedPage, ADMIN_USER, ADMIN_PASS);
    await ensureComponentViaApi(seedPage);
    await seedContext?.close();
  }
}

async function ensureStateDir() {
  if (!fs.existsSync(STATE_DIR)) {
    fs.mkdirSync(STATE_DIR, { recursive: true });
  }
}

export async function saveStorageState(browser: Browser, role: 'admin' | 'student' | 'faculty') {
  await ensureStateDir();
  const statePath = path.join(STATE_DIR, `${role}-state.json`);
  if (fs.existsSync(statePath)) {
    return statePath;
  }
  const creds =
    role === 'admin'
      ? [ADMIN_USER, ADMIN_PASS]
      : role === 'faculty'
        ? [FACULTY_USER, FACULTY_PASS]
        : [STUDENT_USER, STUDENT_PASS];
  const context = await browser.newContext({ baseURL: BASE_URL });
  const page = await context.newPage();
  await login(page, creds[0], creds[1]);
  await context.storageState({ path: statePath });
  await context.close();
  return statePath;
}

export async function authedRequestFromPage(page: Page) {
  const cookies = await page.context().cookies();
  const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
  const csrf = cookies.find((c) => c.name === 'csrftoken')?.value;
  const baseHeaders = {
    Cookie: cookieHeader,
    ...(csrf ? { 'X-CSRFToken': csrf } : {}),
    Referer: BASE_URL,
  };
  return {
    get: (url: string, options: any = {}) =>
      page.request.get(url, {
        ...options,
        headers: { ...baseHeaders, ...(options.headers || {}) },
      }),
    post: (url: string, options: any = {}) =>
      page.request.post(url, {
        ...options,
        headers: { ...baseHeaders, ...(options.headers || {}) },
      }),
  };
}
