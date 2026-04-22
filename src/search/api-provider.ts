import type { SearchDefinition } from '../types/config.js';
import type { RawSearchResult } from '../types/result.js';
import type { SearchProvider } from './provider.js';

const DEFAULT_ENGINE_URL = 'https://lite.duckduckgo.com/lite/';
const DEFAULT_TIMEOUT_MS = 15_000;

const stripTags = (value: string): string =>
  value
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const decodeHtml = (value: string): string =>
  value
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');

const extractResultsFromHtml = (html: string): RawSearchResult[] => {
  const linkRegex = /<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/gi;
  const results: RawSearchResult[] = [];
  const seen = new Set<string>();

  let match: RegExpExecArray | null;
  while ((match = linkRegex.exec(html)) !== null) {
    const [full, hrefRaw, titleRaw] = match;
    const href = decodeHtml(hrefRaw).trim();
    const title = decodeHtml(stripTags(titleRaw));

    if (!href.startsWith('http')) {
      continue;
    }

    if (seen.has(href)) {
      continue;
    }

    const snippetBlock = html.slice(match.index + full.length, match.index + full.length + 400);
    const snippet = decodeHtml(stripTags(snippetBlock));

    results.push({
      title: title || href,
      url: href,
      snippet
    });
    seen.add(href);
  }

  return results;
};

const searchPage = async (engineUrl: string, query: string, page: number): Promise<RawSearchResult[]> => {
  const url = new URL(engineUrl);
  url.searchParams.set('q', query);
  url.searchParams.set('s', String(page * 30));

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      headers: {
        'user-agent':
          'Mozilla/5.0 (compatible; JobSearchReportBot/1.0; +https://github.com/open-source/job-search-report-automation)'
      },
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`Search request failed: ${response.status} ${response.statusText}`);
    }

    const html = await response.text();
    return extractResultsFromHtml(html);
  } finally {
    clearTimeout(timeout);
  }
};

export class ApiSearchProvider implements SearchProvider {
  readonly name = 'api';

  private readonly engineUrl: string;

  constructor(engineUrl = process.env.SEARCH_ENGINE_URL ?? DEFAULT_ENGINE_URL) {
    this.engineUrl = engineUrl;
  }

  async search(query: string, search: SearchDefinition): Promise<RawSearchResult[]> {
    const pages = Math.max(1, Math.ceil(search.maxResults / 30));
    const aggregated: RawSearchResult[] = [];

    for (let page = 0; page < pages; page += 1) {
      const pageResults = await searchPage(this.engineUrl, query, page);
      if (pageResults.length === 0) {
        break;
      }

      aggregated.push(...pageResults);
      if (aggregated.length >= search.maxResults) {
        break;
      }
    }

    return aggregated.slice(0, search.maxResults);
  }
}

export { extractResultsFromHtml };
