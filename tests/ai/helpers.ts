import { APIRequestContext, expect } from '@playwright/test';

export const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
export const ADMIN_IDENTITY = process.env.ADMIN_IDENTITY || 'labadmin1';
export const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'LabAdmin@123';

export async function getAdminToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${BASE_URL}/api/auth/token/`, {
    data: { identity: ADMIN_IDENTITY, password: ADMIN_PASSWORD },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.token;
}

export async function askAI(request: APIRequestContext, query: string): Promise<string> {
  const token = await getAdminToken(request);
  const resp = await request.post(`${BASE_URL}/api/ai/query/`, {
    headers: { Authorization: `Token ${token}` },
    data: { query },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.answer as string;
}

export function keywordScore(answer: string, keywords: string[]): number {
  const lower = answer.toLowerCase();
  const hits = keywords.filter((k) => lower.includes(k.toLowerCase())).length;
  return keywords.length ? hits / keywords.length : 0;
}
