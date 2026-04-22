import { describe, expect, it } from 'vitest';
import { matchRules } from '../../src/filters/match-rules.js';
import { normalizeResult } from '../../src/normalize/normalize-result.js';
import config from '../../searches.json' with { type: 'json' };

describe('matchRules', () => {
  it('detects include and allOf matches', () => {
    const result = normalizeResult({
      title: 'Senior Frontend Engineer',
      url: 'https://jobs.example.com/1',
      snippet: 'Remote role in Brazil with React and TypeScript'
    });

    const matches = matchRules(result, config.searches[0]);
    expect(matches.hasAllOf).toBe(true);
    expect(matches.matchedIncludeTerms).toContain('react');
  });
});
