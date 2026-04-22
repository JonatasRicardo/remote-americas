import type { SearchDefinition } from '../types/config.js';
import type { NormalizedResult } from '../types/result.js';
import { includesTerm } from '../utils/text.js';

const combinedText = (result: NormalizedResult): string => `${result.title} ${result.snippet}`;

export const matchRules = (result: NormalizedResult, search: SearchDefinition) => {
  const text = combinedText(result);
  const matchedIncludeTerms = search.include.filter((term) => includesTerm(text, term));
  const matchedExcludeTerms = [...search.exclude, ...search.noneOf].filter((term) =>
    includesTerm(text, term)
  );
  const matchedAllOf = search.allOf.filter((term) => includesTerm(text, term));

  return {
    matchedIncludeTerms,
    matchedExcludeTerms,
    matchedAllOf,
    hasAllOf: matchedAllOf.length === search.allOf.length,
    hasInclude: search.include.length === 0 || matchedIncludeTerms.length > 0
  };
};
