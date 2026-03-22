import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';

test.describe('Login form UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/accounts/login/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('form');
  });

  test('fields are present with correct types', async ({ page }) => {
    const username = page.locator('input[name="username"]');
    const password = page.locator('input[name="password"]');
    await expect(username).toBeVisible();
    await expect(password).toBeVisible();
    await expect(password).toHaveAttribute('type', 'password');
  });

  test('shows validation error when submitted empty', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Login' })).toBeDisabled();
    await page.locator('input[name="username"]').fill(' ');
    await page.locator('input[name="password"]').fill(' ');
    await expect(page.getByRole('button', { name: 'Login' })).toBeDisabled();

    // Fill only one field to ensure still disabled
    await page.locator('input[name="username"]').fill('someone');
    await expect(page.getByRole('button', { name: 'Login' })).toBeDisabled();

    // Fill both to enable, then clear to trigger server validation
    await page.locator('input[name="password"]').fill('bad');
    await expect(page.getByRole('button', { name: 'Login' })).toBeEnabled();
    await page.locator('input[name="username"]').fill('');
    await page.locator('input[name="password"]').fill('');
    await expect(page.getByRole('button', { name: 'Login' })).toBeDisabled();

    // Submit empty via JS to assert server-side error
    await page.locator('input[name="username"]').fill('');
    await page.locator('input[name="password"]').fill('');
    await page.getByRole('button', { name: 'Login' }).evaluate((btn: HTMLButtonElement) => (btn.disabled = false));
    await page.getByRole('button', { name: 'Login' }).click();
    await page.waitForSelector('.alert.alert-danger, form');
    await expect(page.locator('.alert.alert-danger')).toContainText('Unable to sign in');
  });
});
