import type { SearchProvider } from './provider.js';
import type { RawSearchResult } from '../types/result.js';
import type { SearchDefinition } from '../types/config.js';

export class MockSearchProvider implements SearchProvider {
  readonly name = 'mock';

  constructor(private readonly fixtureMap: Record<string, RawSearchResult[]>) {}

  async search(_query: string, search: SearchDefinition): Promise<RawSearchResult[]> {
    return this.fixtureMap[search.id] ?? [];
  }
}
