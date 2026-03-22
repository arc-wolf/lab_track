import { test, expect } from '@playwright/test';
import { askAI, keywordScore } from './helpers';

test.describe('AI scoring', () => {
  test('overdue query yields relevant content with score > 0.5', async ({ request }) => {
    const answer = await askAI(request, 'Show overdue requests');
    const score = keywordScore(answer, ['overdue', 'request', 'status', 'pending']);
    expect(score).toBeGreaterThan(0.5);
  });
});
