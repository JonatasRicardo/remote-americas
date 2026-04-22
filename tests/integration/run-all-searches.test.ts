import { describe, expect, it } from 'vitest';
import { runAllSearches } from '../../src/pipeline/run-all-searches.js';
import { MockSearchProvider } from '../../src/search/mock-provider.js';
import { Logger } from '../../src/utils/logger.js';
import config from '../../searches.json' with { type: 'json' };
import fixtures from '../fixtures/mock-results.json' with { type: 'json' };

describe('runAllSearches', () => {
  it('runs all searches in dry-run mode', async () => {
    const provider = new MockSearchProvider(fixtures);
    const runs = await runAllSearches(config, provider, { dryRun: true, debug: false }, new Logger());

    expect(runs).toHaveLength(2);
    expect(runs[0].definition.id).toBe('frontend-remote-br');
  });
});
