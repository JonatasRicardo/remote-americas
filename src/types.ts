export interface SearchConfig {
  id: string;
  title: string;
  filename: string;
  sites: string[];
  include: string[];
  exclude: string[];
  allOf: string[];
  anyOf: string[];
  noneOf: string[];
  maxResults: number;
}

export interface AppConfig {
  output: {
    reportsDir: string;
    indexFile: string;
    jsonDir: string;
  };
  searches: SearchConfig[];
}

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
  sourceDomain: string;
  matchedIncludeTerms: string[];
  matchedExcludeTerms: string[];
  score: number;
  accepted: boolean;
  rejectionReason?: string;
}

export interface SearchRun {
  search: SearchConfig;
  query: string;
  generatedAt: string;
  collected: number;
  duplicatesRemoved: number;
  accepted: SearchResult[];
  rejected: SearchResult[];
}

export interface CliOptions {
  configPath: string;
  dryRun: boolean;
  debug: boolean;
  provider: 'api' | 'mock';
  fixturesPath: string;
}
