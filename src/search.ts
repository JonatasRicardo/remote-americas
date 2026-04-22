import { readFile } from 'node:fs/promises';
import type { CliOptions, SearchConfig, SearchResult } from './types.js';

const quote = (value: string): string => `"${value}"`;
const text = (result: Pick<SearchResult, 'title' | 'snippet'>): string =>
  `${result.title} ${result.snippet}`.toLowerCase();

export const buildQuery = (search: SearchConfig): string => {
  const parts: string[] = [];
  parts.push(`(${search.sites.map((s) => `site:${s}`).join(' OR ')})`);
  parts.push(...search.allOf.map(quote));
  if (search.include.length) parts.push(`(${search.include.map(quote).join(' OR ')})`);
  if (search.anyOf.length) parts.push(`(${search.anyOf.map(quote).join(' OR ')})`);
  const negatives = [...search.exclude, ...search.noneOf];
  parts.push(...negatives.map((t) => `-${quote(t)}`));
  return parts.join(' ');
};

interface GoogleSearchItem {
  title?: string;
  link?: string;
  snippet?: string;
}

interface GoogleSearchResponse {
  items?: GoogleSearchItem[];
}

const parseGoogleResponse = (payload: GoogleSearchResponse): Array<{ title: string; url: string; snippet: string }> => {
  const items = payload.items ?? [];
  return items
    .map((item) => ({
      title: (item.title ?? '').trim(),
      url: (item.link ?? '').trim(),
      snippet: (item.snippet ?? '').trim()
    }))
    .filter((item) => item.url.startsWith('http'));
};

const searchGoogle = async (
  query: string,
  maxResults: number
): Promise<Array<{ title: string; url: string; snippet: string }>> => {
  const apiKey = process.env.GOOGLE_API_KEY;
  const cx = process.env.GOOGLE_CSE_ID;

  if (!apiKey || !cx) {
    throw new Error(
      'Missing GOOGLE_API_KEY or GOOGLE_CSE_ID. Configure Google Custom Search JSON API credentials.'
    );
  }

  const collected: Array<{ title: string; url: string; snippet: string }> = [];

  for (let start = 1; start <= maxResults && start <= 91; start += 10) {
    const url = new URL('https://www.googleapis.com/customsearch/v1');
    url.searchParams.set('key', apiKey);
    url.searchParams.set('cx', cx);
    url.searchParams.set('q', query);
    url.searchParams.set('start', String(start));
    url.searchParams.set('num', String(Math.min(10, maxResults - collected.length)));

    const response = await fetch(url, {
      headers: {
        'user-agent': 'job-search-reporter/1.0'
      }
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Google API error: ${response.status} ${response.statusText} - ${body}`);
    }

    const payload = (await response.json()) as GoogleSearchResponse;
    const batch = parseGoogleResponse(payload);

    if (batch.length === 0) break;

    collected.push(...batch);

    if (collected.length >= maxResults) break;
  }

  return collected.slice(0, maxResults);
};

const loadMock = async (
  fixturesPath: string,
  searchId: string
): Promise<Array<{ title: string; url: string; snippet: string }>> => {
  const content = await readFile(fixturesPath, 'utf8');
  const data = JSON.parse(content) as Record<string, Array<{ title: string; url: string; snippet: string }>>;
  return data[searchId] ?? [];
};

const score = (result: SearchResult, search: SearchConfig): number => {
  let points = 50;
  points += result.matchedIncludeTerms.length * 10;
  points += search.allOf.filter((t) => text(result).includes(t.toLowerCase())).length * 8;
  points -= result.matchedExcludeTerms.length * 30;
  return Math.max(0, Math.min(points, 100));
};

const canonical = (url: string): string => {
  const u = new URL(url);
  u.hash = '';
  u.search = '';
  return u.toString().toLowerCase();
};

export const executeSearch = async (
  search: SearchConfig,
  options: CliOptions
): Promise<{ query: string; collected: SearchResult[]; duplicatesRemoved: number }> => {
  const query = buildQuery(search);
  const raw =
    options.provider === 'mock'
      ? await loadMock(options.fixturesPath, search.id)
      : await searchGoogle(query, search.maxResults * 2);

  const seen = new Set<string>();
  let duplicatesRemoved = 0;
  const collected: SearchResult[] = [];

  for (const item of raw) {
    const sourceDomain = new URL(item.url).hostname.replace(/^www\./, '');
    const candidate: SearchResult = {
      title: item.title,
      url: item.url,
      snippet: item.snippet,
      sourceDomain,
      matchedIncludeTerms: search.include.filter((t) => text(item).includes(t.toLowerCase())),
      matchedExcludeTerms: [...search.exclude, ...search.noneOf].filter((t) =>
        text(item).includes(t.toLowerCase())
      ),
      score: 0,
      accepted: false
    };

    const key = canonical(candidate.url);
    if (seen.has(key)) {
      duplicatesRemoved += 1;
      continue;
    }
    seen.add(key);

    candidate.score = score(candidate, search);

    const hasAll = search.allOf.every((t) => text(candidate).includes(t.toLowerCase()));
    const hasInclude = search.include.length === 0 || candidate.matchedIncludeTerms.length > 0;

    if (candidate.matchedExcludeTerms.length > 0) {
      candidate.rejectionReason = 'matched exclusion';
    } else if (!hasAll) {
      candidate.rejectionReason = 'missing allOf';
    } else if (!hasInclude) {
      candidate.rejectionReason = 'missing include';
    } else if (candidate.score < 55) {
      candidate.rejectionReason = 'low score';
    } else {
      candidate.accepted = true;
    }

    collected.push(candidate);
  }

  return { query, collected, duplicatesRemoved };
};

export { parseGoogleResponse };
