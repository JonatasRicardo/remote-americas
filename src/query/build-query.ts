import type { SearchDefinition } from '../types/config.js';
import type { QueryBuildResult } from '../types/result.js';

const quote = (term: string): string => `"${term}"`;

const buildOrGroup = (items: string[]): string => {
  if (items.length === 0) {
    return '';
  }
  if (items.length === 1) {
    return quote(items[0]);
  }
  return `(${items.map(quote).join(' OR ')})`;
};

export const buildQuery = (search: SearchDefinition): QueryBuildResult => {
  const parts: string[] = [];
  const debugParts: string[] = [];

  const sites = search.sites.map((site) => `site:${site}`).join(' OR ');
  parts.push(`(${sites})`);
  debugParts.push('sites');

  if (search.allOf.length > 0) {
    parts.push(...search.allOf.map(quote));
    debugParts.push('allOf');
  }

  const includeOr = buildOrGroup(search.include);
  if (includeOr) {
    parts.push(includeOr);
    debugParts.push('include');
  }

  const anyOfOr = buildOrGroup(search.anyOf);
  if (anyOfOr) {
    parts.push(anyOfOr);
    debugParts.push('anyOf');
  }

  const negatives = [...search.exclude, ...search.noneOf];
  if (negatives.length > 0) {
    parts.push(...negatives.map((term) => `-${quote(term)}`));
    debugParts.push('negative');
  }

  return {
    query: parts.join(' '),
    debugParts
  };
};
