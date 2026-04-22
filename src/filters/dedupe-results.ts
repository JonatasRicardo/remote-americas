import type { NormalizedResult } from '../types/result.js';

export const dedupeResults = (results: NormalizedResult[]) => {
  const seen = new Set<string>();
  const unique: NormalizedResult[] = [];
  const duplicates: NormalizedResult[] = [];

  for (const result of results) {
    if (seen.has(result.canonicalUrl)) {
      duplicates.push({ ...result, accepted: false, rejectionReason: 'duplicate' });
      continue;
    }
    seen.add(result.canonicalUrl);
    unique.push(result);
  }

  return { unique, duplicates };
};
