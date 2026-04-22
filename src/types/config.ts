export interface OutputConfig {
  reportsDir: string;
  indexFile: string;
  jsonDir: string;
}

export interface SearchDefinition {
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

export interface SearchesConfig {
  output: OutputConfig;
  searches: SearchDefinition[];
}
