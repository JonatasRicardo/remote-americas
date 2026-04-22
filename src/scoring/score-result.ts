import type { SearchDefinition } from '../types/config.js';
import type { NormalizedResult } from '../types/result.js';
import { includesTerm } from '../utils/text.js';

const aggregatorSignals = ['indeed', 'ziprecruiter', 'glassdoor', 'monster'];

export const scoreResult = (result: NormalizedResult, search: SearchDefinition): number => {
  const text = `${result.title} ${result.snippet}`.toLowerCase();
  let score = 50;

  score += result.matchedIncludeTerms.length * 10;
  score += search.allOf.filter((term) => includesTerm(text, term)).length * 8;
  score += search.anyOf.filter((term) => includesTerm(text, term)).length * 5;
  score -= result.matchedExcludeTerms.length * 25;

  if (aggregatorSignals.some((signal) => result.sourceDomain.includes(signal))) {
    score -= 20;
  } else {
    score += 5;
  }

  return Math.max(0, Math.min(100, score));
};
