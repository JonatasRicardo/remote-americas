import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { extractResultsFromHtml } from '../../src/search/api-provider.js';

describe('extractResultsFromHtml', () => {
  it('extracts only external http links', async () => {
    const html = await readFile(resolve('./tests/fixtures/search-engine-sample.html'), 'utf8');
    const results = extractResultsFromHtml(html);

    expect(results).toHaveLength(2);
    expect(results[0].url).toContain('greenhouse.io');
    expect(results[0].snippet).toContain('Remote role in Brazil');
  });
});
