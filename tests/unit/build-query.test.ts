import { describe, expect, it } from 'vitest';
import { buildQuery } from '../../src/query/build-query.js';
import config from '../../searches.json' with { type: 'json' };

describe('buildQuery', () => {
  it('builds deterministic query', () => {
    const result = buildQuery(config.searches[0]);
    expect(result.query).toContain('site:greenhouse.io OR site:lever.co OR site:ashbyhq.com');
    expect(result.query).toContain('"remote" "brazil"');
    expect(result.query).toContain('-"ios"');
  });
});
