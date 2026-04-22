import type { SearchDefinition } from '../types/config.js';
import type { RawSearchResult } from '../types/result.js';
import type { SearchProvider } from './provider.js';
import { ApiSearchProvider } from './api-provider.js';

/**
 * BrowserSearchProvider is reserved for future Playwright-first crawling.
 * For now, it delegates to ApiSearchProvider so "real search" works out of the box.
 */
export class BrowserSearchProvider implements SearchProvider {
  readonly name = 'browser';

  private readonly delegate = new ApiSearchProvider();

  async search(query: string, search: SearchDefinition): Promise<RawSearchResult[]> {
    return this.delegate.search(query, search);
  }
}
