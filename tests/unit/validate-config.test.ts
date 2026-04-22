import { describe, expect, it } from 'vitest';
import { validateConfig } from '../../src/config/validate-config.js';
import configFixture from '../../searches.json' with { type: 'json' };

describe('validateConfig', () => {
  it('accepts valid config', () => {
    expect(() => validateConfig(configFixture)).not.toThrow();
  });

  it('rejects invalid config', () => {
    expect(() => validateConfig({ searches: [] })).toThrowError(/Invalid config/);
  });
});
