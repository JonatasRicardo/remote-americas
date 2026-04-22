import { describe, expect, it } from 'vitest';
import { scoreResult } from '../../src/scoring/score-result.js';
import { normalizeResult } from '../../src/normalize/normalize-result.js';
import config from '../../searches.json' with { type: 'json' };

describe('scoreResult', () => {
  it('scores relevant result higher', () => {
    const result = normalizeResult({
      title: 'Backend Engineer Remote United States',
      url: 'https://jobs.lever.co/company/1',
      snippet: 'Node.js and TypeScript role'
    });
    result.matchedIncludeTerms = ['backend', 'node.js', 'typescript'];
    const score = scoreResult(result, config.searches[1]);
    expect(score).toBeGreaterThan(70);
  });
});
