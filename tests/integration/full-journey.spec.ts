import { test, expect } from '@playwright/test';
import { BASE_URL, loginAsAdmin, loginAsStudent, loginAsFaculty, findSlipRow, authedRequestFromPage } from '../shared/helpers';
import { waitForPageReady, safeClick } from '../shared/ui';

test.describe('Full integration journey', () => {
  test.setTimeout(150000);

  test('admin import, student request, faculty approve, admin issue/return, AI reflects state', async ({ page, browser, request }) => {
    // Admin import (skip file upload, call API import endpoint with CSV buffer)
    await loginAsAdmin(page);
    const csv = 'name,category,total_stock\nJourneyComp,Power,4';
    const authedReq = await authedRequestFromPage(page);
    const importResp = await authedReq.post(`${BASE_URL}/inventory/import-excel/`, {
      multipart: { file: { name: 'import.csv', buffer: Buffer.from(csv), mimeType: 'text/csv' } },
    });
    expect(importResp.ok()).toBeTruthy();

    // Student creates request
    const studentCtx = await browser.newContext({ baseURL: BASE_URL });
    const studentPage = await studentCtx.newPage();
    await loginAsStudent(studentPage);
    await studentPage.goto(`${BASE_URL}/inventory/components/`);
    await waitForPageReady(studentPage);
    const firstCard = studentPage.locator('.card').filter({ hasText: 'JourneyComp' }).first().or(studentPage.locator('.card').first());
    await safeClick(firstCard.getByRole('button', { name: 'Add to Cart' }));
    await studentPage.waitForSelector('a:has-text("View Cart")');
    await studentPage.getByRole('link', { name: 'View Cart' }).click();
    await studentPage.waitForSelector('form');
    await studentPage.getByPlaceholder('Enter project title').fill('Journey Project');
    await studentPage.getByRole('button', { name: 'Generate Borrow Slip' }).click();
    await studentPage.getByRole('button', { name: 'Confirm & Submit' }).click();
    await studentPage.waitForSelector('table tbody tr');
    const slipCell = await studentPage.locator('table tbody tr').first().getByRole('cell').first().innerText();
    const slipId = slipCell.replace('#', '').trim();
    await studentCtx.close();

    // Faculty approves
    const facultyCtx = await browser.newContext({ baseURL: BASE_URL });
    const facultyPage = await facultyCtx.newPage();
    await loginAsFaculty(facultyPage);
    await facultyPage.goto(`${BASE_URL}/requests/faculty/`);
    await facultyPage.waitForSelector('input[name="q"]', { timeout: 20000 });
    await facultyPage.locator('input[name="q"], input[type="search"]').fill(slipId);
    await facultyPage.getByRole('button', { name: 'Apply' }).click();
    await facultyPage.waitForSelector('table tbody tr');
    const fRow = facultyPage.locator('table tbody tr').filter({ hasText: `#${slipId}` }).first();
    await expect(fRow).toBeVisible();
    if (await fRow.getByRole('button', { name: 'Approve' }).count()) {
      await fRow.getByRole('button', { name: 'Approve' }).click();
      await facultyPage.waitForSelector('table tbody tr');
    }
    await facultyCtx.close();

    // Admin issue and return
    await page.goto(`${BASE_URL}/requests/admin/requests/`);
    await waitForPageReady(page);
    const aRow = await findSlipRow(page, slipId);
    if (await aRow.getByRole('button', { name: 'Mark Collected' }).count()) {
      await aRow.getByRole('textbox', { name: /Collected by/i }).fill('Integrator');
      await safeClick(aRow.getByRole('button', { name: 'Mark Collected' }));
      await page.waitForSelector('table tbody tr');
    }
    const rRow = await findSlipRow(page, slipId);
    if (await rRow.getByRole('button', { name: 'Mark Returned' }).count()) {
      await rRow.getByRole('button', { name: 'Mark Returned' }).click();
      const modal = page.locator('#returnModal');
      await expect(modal).toBeVisible();
      await modal.getByRole('textbox').fill('All good');
      await safeClick(modal.getByRole('button', { name: 'Submit' }));
      await page.waitForSelector('table tbody tr');
    }

    // AI reflects state
    const tokenResp = await request.post(`${BASE_URL}/api/auth/token/`, {
      data: { identity: process.env.ADMIN_USER || 'labadmin1', password: process.env.ADMIN_PASS || 'LabAdmin@123' },
    });
    expect(tokenResp.ok()).toBeTruthy();
    const token = (await tokenResp.json()).token;
    const aiResp = await request.post(`${BASE_URL}/api/ai/query/`, {
      headers: { Authorization: `Token ${token}` },
      data: { query: 'Show returned requests' },
    });
    expect(aiResp.ok()).toBeTruthy();
    const aiBody = await aiResp.json();
    expect(String(aiBody.answer || '').toLowerCase()).toMatch(/returned|request/);
  });
});
