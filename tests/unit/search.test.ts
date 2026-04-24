import { describe, expect, it } from 'vitest';
import { buildQuery, executeSearch, parseGoogleResponse } from '../../src/search.js';
import config from '../../searches.json' with { type: 'json' };

describe('search helpers', () => {
  it('builds query with site operator', () => {
    const q = buildQuery(config.searches[0]);
    expect(q).toContain('site:greenhouse.io');
  });

  it('runs mock search', async () => {
    const result = await executeSearch(config.searches[0], {
      configPath: './searches.json',
      dryRun: true,
      debug: false,
      provider: 'mock',
      fixturesPath: './tests/fixtures/mock-results.json'
    });

    expect(result.collected.length).toBeGreaterThan(0);
  });

  it('parses google payload', () => {
    const parsed = parseGoogleResponse({
      items: [
        { title: 'A', link: 'https://example.com/a', snippet: 'One' },
        { title: 'B', link: '/internal', snippet: 'Two' }
      ]
    });

    expect(parsed).toHaveLength(1);
    expect(parsed[0].url).toBe('https://example.com/a');
  });
});
