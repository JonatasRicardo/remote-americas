import { describe, expect, it } from 'vitest';
import { generateReportMarkdown } from '../../src/generators/generate-report-markdown.js';

describe('generateReportMarkdown', () => {
  it('renders markdown with stats', () => {
    const markdown = generateReportMarkdown({
      definition: {
        id: 'id',
        title: 'Title',
        filename: 'report.md',
        sites: [],
        include: [],
        exclude: [],
        allOf: [],
        anyOf: [],
        noneOf: [],
        maxResults: 10
      },
      query: 'site:example.com',
      generatedAt: '2026-01-01T00:00:00.000Z',
      stats: { totalCollected: 1, duplicatesRemoved: 0, totalAfterFiltering: 1 },
      accepted: [
        {
          title: 'Role',
          url: 'https://example.com/job',
          canonicalUrl: 'https://example.com/job',
          snippet: 'snippet',
          sourceDomain: 'example.com',
          matchedIncludeTerms: ['typescript'],
          matchedExcludeTerms: [],
          score: 90,
          accepted: true
        }
      ],
      rejected: []
    });

    expect(markdown).toContain('# Title');
    expect(markdown).toContain('## Stats');
  });
});
