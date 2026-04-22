import { describe, expect, it } from 'vitest';
import { dedupeResults } from '../../src/filters/dedupe-results.js';
import { normalizeResult } from '../../src/normalize/normalize-result.js';

describe('dedupeResults', () => {
  it('deduplicates by canonical url', () => {
    const r1 = normalizeResult({ title: 'A', url: 'https://a.com/job?id=1', snippet: 'x' });
    const r2 = normalizeResult({ title: 'B', url: 'https://a.com/job?id=2', snippet: 'x' });
    const { unique, duplicates } = dedupeResults([r1, r2]);
    expect(unique).toHaveLength(1);
    expect(duplicates).toHaveLength(1);
  });
});
