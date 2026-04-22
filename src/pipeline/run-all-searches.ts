import type { SearchesConfig } from '../types/config.js';
import type { SearchProvider } from '../search/provider.js';
import type { SearchRunOutput } from '../types/result.js';
import { runSearch } from './run-search.js';
import { generateIndexMarkdown } from '../generators/generate-index-markdown.js';
import { writeFileIfChanged } from '../utils/file.js';
import { nowIso } from '../utils/time.js';
import { Logger } from '../utils/logger.js';

export interface RunAllOptions {
  dryRun?: boolean;
  debug?: boolean;
}

export const runAllSearches = async (
  config: SearchesConfig,
  provider: SearchProvider,
  options: RunAllOptions,
  logger: Logger
): Promise<SearchRunOutput[]> => {
  const runs: SearchRunOutput[] = [];
  for (const search of config.searches) {
    const run = await runSearch(
      search,
      provider,
      {
        dryRun: options.dryRun,
        debug: options.debug,
        reportsDir: config.output.reportsDir,
        jsonDir: config.output.jsonDir
      },
      logger
    );
    runs.push(run);
  }

  if (!options.dryRun) {
    const indexMarkdown = generateIndexMarkdown(runs, nowIso());
    await writeFileIfChanged(config.output.indexFile, indexMarkdown);
  }

  return runs;
};
