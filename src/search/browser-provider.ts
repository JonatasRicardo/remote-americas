import type { SearchDefinition } from '../types/config.js';
import type { RawSearchResult } from '../types/result.js';
import type { SearchProvider } from './provider.js';

export class BrowserSearchProvider implements SearchProvider {
  readonly name = 'browser';

  async search(_query: string, _search: SearchDefinition): Promise<RawSearchResult[]> {
    throw new Error('BrowserSearchProvider is a placeholder. Implement Playwright-backed search logic.');
  }
}
