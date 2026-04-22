import type { SearchDefinition } from '../types/config.js';
import type { NormalizedResult } from '../types/result.js';
import { matchRules } from './match-rules.js';
import { scoreResult } from '../scoring/score-result.js';

export const filterResults = (
  results: NormalizedResult[],
  search: SearchDefinition,
  debug = false
): { accepted: NormalizedResult[]; rejected: NormalizedResult[] } => {
  const accepted: NormalizedResult[] = [];
  const rejected: NormalizedResult[] = [];

  for (const result of results) {
    const matches = matchRules(result, search);
    result.matchedIncludeTerms = matches.matchedIncludeTerms;
    result.matchedExcludeTerms = matches.matchedExcludeTerms;
    result.score = scoreResult(result, search);

    if (matches.matchedExcludeTerms.length > 0) {
      result.accepted = false;
      result.rejectionReason = 'matched exclusion term';
      rejected.push(result);
      continue;
    }

    if (!matches.hasAllOf) {
      result.accepted = false;
      result.rejectionReason = 'missing allOf terms';
      rejected.push(result);
      continue;
    }

    if (!matches.hasInclude) {
      result.accepted = false;
      result.rejectionReason = 'missing include terms';
      rejected.push(result);
      continue;
    }

    if (result.score < 55) {
      result.accepted = false;
      result.rejectionReason = 'score below threshold';
      rejected.push(result);
      continue;
    }

    result.accepted = true;
    accepted.push(result);

    if (debug) {
      result.rejectionReason = undefined;
    }
  }

  return { accepted, rejected };
};
