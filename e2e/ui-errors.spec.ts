import { test, expect } from '@playwright/test';
import { ensureComponentExists, ensureInventoryHasCards } from '../tests/shared/helpers';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const STUDENT_USER = process.env.STUDENT_USER || 'student01';
const STUDENT_PASS = process.env.STUDENT_PASS || 'Student@123';

async function loginStudent(page) {
  await page.goto(`${BASE_URL}/accounts/login/`);
  await page.waitForLoadState('domcontentloaded');
  await page.locator('input[name="username"]').fill(STUDENT_USER);
  await page.locator('input[name="password"]').fill(STUDENT_PASS);
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForSelector('body');
}

test.describe('Error handling UI surfaces', () => {
  test('403 page shows expected copy (CSRF failure)', async ({ page }) => {
    // Unauthenticated POST without CSRF token should trigger CSRF 403 page
    const resp = await page.request.post(`${BASE_URL}/inventory/cart/generate/`, {
      form: { project_title: 'bad' },
      failOnStatusCode: false,
    });
    expect(resp.status()).toBe(403);
    const body = await resp.text();
    expect(body).toContain('Session expired');
    expect(body).toContain('Security token check failed');
  });

  test('invalid add-to-cart submission shows toast error', async ({ page, browser }) => {
    await ensureInventoryHasCards(page);
    await loginStudent(page);
    await page.goto(`${BASE_URL}/inventory/components/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('.card button', { timeout: 20000 });

    // Grab a component id from the first card
    const firstCard = page.locator('.card').first();
    await expect(firstCard).toBeAttached();
    const qtyInput = firstCard.locator('input[name="quantity"]');
    await expect(qtyInput).toBeAttached();
    await qtyInput.fill('0');
    const form = firstCard.locator('form.quantity-form');
    await form.evaluate((f: HTMLFormElement) => f.submit());
    await page.waitForSelector('.toast-body');

    const toast = page.locator('.toast-body', { hasText: 'Quantity must be greater than zero.' });
    await expect(toast).toBeVisible({ timeout: 7000 });
  });

  test('CSRF failure handled with friendly message when logged in', async ({ page }) => {
    await loginStudent(page);
    const resp = await page.request.post(`${BASE_URL}/inventory/cart/generate/`, {
      form: { project_title: 'CSRF check' },
      failOnStatusCode: false,
      headers: { 'X-CSRFToken': '' }, // explicit bad token
    });
    expect(resp.status()).toBe(403);
    const body = await resp.text();
    expect(body).toContain('Session expired');
    expect(body).toContain('Refresh page');
  });
});
