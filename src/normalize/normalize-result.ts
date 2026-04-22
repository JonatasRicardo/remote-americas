import { canonicalizeUrl } from './canonicalize-url.js';
import type { RawSearchResult, NormalizedResult } from '../types/result.js';

export const normalizeResult = (raw: RawSearchResult): NormalizedResult => {
  const sourceDomain = new URL(raw.url).hostname.replace(/^www\./, '');
  return {
    title: raw.title.trim(),
    url: raw.url.trim(),
    canonicalUrl: canonicalizeUrl(raw.url),
    snippet: raw.snippet.trim(),
    sourceDomain,
    matchedIncludeTerms: [],
    matchedExcludeTerms: [],
    score: 0,
    accepted: false
  };
};
