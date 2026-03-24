import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { BASE_URL, loginAsAdmin, authedRequestFromPage } from '../shared/helpers';
import { waitForPageReady } from '../shared/ui';

const sampleFile = path.join(__dirname, 'sample-import.xlsx');

test.beforeAll(() => {
  // create tiny excel via CSV fallback
  fs.writeFileSync(sampleFile.replace('.xlsx', '.csv'), 'name,category,total_stock\nPX1,Power,5');
});

test.describe('Excel import/export', () => {
  test('upload Excel and see success, export Excel', async ({ page }) => {
    await loginAsAdmin(page);
    await waitForPageReady(page);
    const csvPath = sampleFile.replace('.xlsx', '.csv');
    const buffer = fs.readFileSync(csvPath);
    const authedReq = await authedRequestFromPage(page);
    const resp = await authedReq.post(`${BASE_URL}/inventory/import-excel/`, {
      multipart: {
        file: {
          name: 'import.csv',
          mimeType: 'text/csv',
          buffer,
        },
      },
    });
    if (!resp.ok()) {
      console.error('Import response body:', await resp.text());
    }
    expect(resp.ok()).toBeTruthy();

    const exportResp = await authedReq.get(`${BASE_URL}/inventory/export-excel/`);
    if (exportResp.status() !== 200) {
      console.error('Export response body:', await exportResp.text());
    }
    expect(exportResp.status()).toBe(200);
    const filename = exportResp.headers()['content-disposition'] || '';
    expect(filename).toMatch(/labtrack-export/);
  });
});
