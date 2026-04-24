import { describe, expect, it } from 'vitest';
import { loadConfig } from '../../src/config.js';

describe('loadConfig', () => {
  it('loads default config', async () => {
    const cfg = await loadConfig('./searches.json');
    expect(cfg.searches.length).toBeGreaterThan(0);
  });
});
