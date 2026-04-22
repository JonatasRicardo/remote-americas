import { readFile } from 'node:fs/promises';
import { loadConfig } from './config/load-config.js';
import { MockSearchProvider } from './search/mock-provider.js';
import { BrowserSearchProvider } from './search/browser-provider.js';
import { ApiSearchProvider } from './search/api-provider.js';
import { runAllSearches } from './pipeline/run-all-searches.js';
import { Logger } from './utils/logger.js';
import type { SearchProvider } from './search/provider.js';
import type { RawSearchResult } from './types/result.js';

interface CliOptions {
  config: string;
  debug: boolean;
  dryRun: boolean;
  provider: 'mock' | 'browser' | 'api';
  fixturesPath: string;
}

const parseArgs = (argv: string[]): CliOptions => {
  const options: CliOptions = {
    config: './searches.json',
    debug: false,
    dryRun: false,
    provider: 'api',
    fixturesPath: './tests/fixtures/mock-results.json'
  };

  for (const arg of argv) {
    if (arg.startsWith('--config=')) options.config = arg.replace('--config=', '');
    if (arg === '--debug') options.debug = true;
    if (arg === '--dry-run') options.dryRun = true;
    if (arg.startsWith('--provider=')) {
      const provider = arg.replace('--provider=', '');
      if (provider === 'mock' || provider === 'browser' || provider === 'api') {
        options.provider = provider;
      }
    }
    if (arg.startsWith('--fixtures=')) options.fixturesPath = arg.replace('--fixtures=', '');
  }

  return options;
};

const loadMockFixtures = async (fixturesPath: string): Promise<Record<string, RawSearchResult[]>> => {
  const content = await readFile(fixturesPath, 'utf8');
  return JSON.parse(content) as Record<string, RawSearchResult[]>;
};

const createProvider = async (options: CliOptions): Promise<SearchProvider> => {
  if (options.provider === 'browser') {
    return new BrowserSearchProvider();
  }

  if (options.provider === 'api') {
    return new ApiSearchProvider();
  }

  const fixtures = await loadMockFixtures(options.fixturesPath);
  return new MockSearchProvider(fixtures);
};

const main = async (): Promise<void> => {
  const options = parseArgs(process.argv.slice(2));
  const logger = new Logger({ debug: options.debug });

  const config = await loadConfig(options.config);
  const provider = await createProvider(options);

  logger.info('Starting job search pipeline', {
    config: options.config,
    provider: provider.name,
    dryRun: options.dryRun,
    debug: options.debug
  });

  const runs = await runAllSearches(config, provider, options, logger);
  logger.info('Finished job search pipeline', { reports: runs.length });
};

main().catch((error: unknown) => {
  console.error('[ERROR] Pipeline failed', error);
  process.exitCode = 1;
});
