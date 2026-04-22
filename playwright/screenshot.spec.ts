import { test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('placeholder report screenshot', async ({ page }) => {
  await mkdir('artifacts/screenshots', { recursive: true });
  await page.goto('/');
  await page.screenshot({ path: 'artifacts/screenshots/report-index.png', fullPage: true });
});
