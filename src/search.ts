import { readFile } from 'node:fs/promises';
import type { CliOptions, SearchConfig, SearchResult } from './types.js';

const engineUrl = process.env.SEARCH_ENGINE_URL ?? 'https://lite.duckduckgo.com/lite/';

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

const parseHtmlResults = (html: string): Array<{ title: string; url: string; snippet: string }> => {
  const linkRegex = /<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/gi;
  const items: Array<{ title: string; url: string; snippet: string }> = [];
  const seen = new Set<string>();

  let match: RegExpExecArray | null;
  while ((match = linkRegex.exec(html)) !== null) {
    const [full, hrefRaw, titleRaw] = match;
    const href = hrefRaw.replace(/&amp;/g, '&');
    if (!href.startsWith('http') || seen.has(href)) continue;
    seen.add(href);

    const title = titleRaw.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    const snippet = html
      .slice(match.index + full.length, match.index + full.length + 350)
      .replace(/<[^>]*>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    items.push({ title: title || href, url: href, snippet });
  }

  return items;
};

const searchWeb = async (query: string, maxResults: number): Promise<Array<{ title: string; url: string; snippet: string }>> => {
  const url = new URL(engineUrl);
  url.searchParams.set('q', query);

  const response = await fetch(url, {
    headers: { 'user-agent': 'Mozilla/5.0 (compatible; JobSearchReporter/1.0)' }
  });
  if (!response.ok) throw new Error(`Search engine error: ${response.status} ${response.statusText}`);

  const html = await response.text();
  return parseHtmlResults(html).slice(0, maxResults);
};

const loadMock = async (fixturesPath: string, searchId: string): Promise<Array<{ title: string; url: string; snippet: string }>> => {
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
      : await searchWeb(query, search.maxResults * 2);

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
      matchedExcludeTerms: [...search.exclude, ...search.noneOf].filter((t) => text(item).includes(t.toLowerCase())),
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
