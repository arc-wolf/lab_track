import { test, expect } from '@playwright/test';
import { BASE_URL, login } from '../shared/helpers';

test.describe('Authentication', () => {
  test('login page loads', async ({ page }) => {
    await page.goto(`${BASE_URL}/accounts/login/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('form');
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
  });

  test('valid login works', async ({ page }) => {
    await login(page, process.env.STUDENT_USER || 'student01', process.env.STUDENT_PASS || 'Student@123');
    await expect(page).toHaveURL(/inventory\/components/);
  });

  test('invalid login shows error', async ({ page }) => {
    await page.goto(`${BASE_URL}/accounts/login/`);
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[name="username"]').fill('baduser');
    await page.locator('input[name="password"]').fill('badpass');
    await page.getByRole('button', { name: 'Login' }).click();
    await page.waitForSelector('.alert-danger');
    await expect(page.locator('.alert-danger')).toContainText(/Unable to sign in/i);
  });
});
