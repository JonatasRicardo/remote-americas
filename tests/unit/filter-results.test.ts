import { describe, expect, it } from 'vitest';
import { filterResults } from '../../src/filters/filter-results.js';
import { normalizeResult } from '../../src/normalize/normalize-result.js';
import config from '../../searches.json' with { type: 'json' };

describe('filterResults', () => {
  it('filters out excluded content', () => {
    const acceptedCandidate = normalizeResult({
      title: 'Backend Engineer',
      url: 'https://jobs.example.com/a',
      snippet: 'Remote united states node.js typescript'
    });
    const rejectedCandidate = normalizeResult({
      title: 'Wordpress Internship',
      url: 'https://jobs.example.com/b',
      snippet: 'Remote united states backend internship'
    });

    const { accepted, rejected } = filterResults(
      [acceptedCandidate, rejectedCandidate],
      config.searches[1]
    );

    expect(accepted).toHaveLength(1);
    expect(rejected).toHaveLength(1);
    expect(rejected[0].rejectionReason).toMatch(/exclusion/);
  });
});
