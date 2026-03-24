import { expect, Locator, Page } from '@playwright/test';

export async function waitForPageReady(page: Page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForSelector('body', { state: 'attached', timeout: 15000 });
}

export async function safeClick(target: Locator) {
  await expect(target).toBeVisible({ timeout: 10000 });
  await target.click();
}

export async function safeFill(target: Locator, value: string) {
  await expect(target).toBeVisible({ timeout: 10000 });
  await target.fill(value);
}

export function getFirstRow(page: Page) {
  return page.locator('table tbody tr').first();
}
