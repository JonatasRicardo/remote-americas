import type { SearchDefinition } from '../types/config.js';
import type { RawSearchResult } from '../types/result.js';
import type { SearchProvider } from './provider.js';

export class ApiSearchProvider implements SearchProvider {
  readonly name = 'api';

  async search(_query: string, _search: SearchDefinition): Promise<RawSearchResult[]> {
    throw new Error('ApiSearchProvider is a placeholder. Implement API client and auth via environment variables.');
  }
}
