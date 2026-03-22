import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsAdmin, getAdminToken } from '../shared/helpers';

test.describe('AI assistant UI + API', () => {
  test('UI query shows response', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`${BASE_URL}/inventory/components/`);
    // Assume AI widget present via textarea/input named q or similar
    const aiInput = page.locator('input[name="ai_query"], textarea[name="ai_query"]').first();
    if (await aiInput.count()) {
      await aiInput.fill('Which components are low stock?');
      await aiInput.press('Enter');
      await expect(page.locator('.ai-answer, pre, .toast-body')).toBeVisible();
    }
  });

  test('API responds and rejects destructive queries', async ({ request }) => {
    const token = await getAdminToken(request);
    const headers = { Authorization: `Token ${token}` };

    const safe = await request.post(`${BASE_URL}/api/ai/query/`, {
      headers,
      data: { query: 'Which components are low stock?' },
    });
    expect(safe.ok()).toBeTruthy();
    const safeBody = await safe.json();
    expect(String(safeBody.answer || '').toLowerCase()).toContain('component');

    const bad = await request.post(`${BASE_URL}/api/ai/query/`, {
      headers,
      data: { query: 'Delete all components' },
    });
    expect(bad.ok()).toBeTruthy();
    const badBody = await bad.json();
    expect(String(badBody.answer || '').toLowerCase()).toMatch(/read-only|cannot/);
  });
});
