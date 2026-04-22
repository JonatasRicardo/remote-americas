import type { SearchDefinition } from './config.js';

export interface RawSearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface NormalizedResult {
  title: string;
  url: string;
  canonicalUrl: string;
  snippet: string;
  sourceDomain: string;
  matchedIncludeTerms: string[];
  matchedExcludeTerms: string[];
  score: number;
  accepted: boolean;
  rejectionReason?: string;
}

export interface QueryBuildResult {
  query: string;
  debugParts: string[];
}

export interface SearchRunStats {
  totalCollected: number;
  duplicatesRemoved: number;
  totalAfterFiltering: number;
}

export interface SearchRunOutput {
  definition: SearchDefinition;
  query: string;
  generatedAt: string;
  stats: SearchRunStats;
  accepted: NormalizedResult[];
  rejected: NormalizedResult[];
}
