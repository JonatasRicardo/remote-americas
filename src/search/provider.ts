import type { SearchDefinition } from '../types/config.js';
import type { RawSearchResult } from '../types/result.js';

export interface SearchProvider {
  readonly name: string;
  search(query: string, search: SearchDefinition): Promise<RawSearchResult[]>;
}
