#!/usr/bin/env node
import { loadConfig } from './config.js';
import { executeSearch } from './search.js';
import { writeOutputs } from './output.js';
import type { CliOptions, SearchRun } from './types.js';

const parseArgs = (): CliOptions => {
  const args = process.argv.slice(2);
  const options: CliOptions = {
    configPath: './searches.json',
    dryRun: false,
    debug: false,
    provider: 'api',
    fixturesPath: './tests/fixtures/mock-results.json'
  };

  for (const arg of args) {
    if (arg === '--dry-run') options.dryRun = true;
    else if (arg === '--debug') options.debug = true;
    else if (arg.startsWith('--config=')) options.configPath = arg.split('=')[1] ?? options.configPath;
    else if (arg.startsWith('--provider=')) {
      const p = arg.split('=')[1];
      if (p === 'api' || p === 'mock') options.provider = p;
    } else if (arg.startsWith('--fixtures=')) options.fixturesPath = arg.split('=')[1] ?? options.fixturesPath;
  }

  return options;
};

const main = async (): Promise<void> => {
  const options = parseArgs();
  const config = await loadConfig(options.configPath);

  console.log(`[info] Running ${config.searches.length} searches with provider=${options.provider}`);

  const runs: SearchRun[] = [];

  for (const search of config.searches) {
    console.log(`[info] Searching: ${search.id}`);
    const { query, collected, duplicatesRemoved } = await executeSearch(search, options);
    const accepted = collected.filter((r) => r.accepted).sort((a, b) => b.score - a.score).slice(0, search.maxResults);
    const rejected = collected.filter((r) => !r.accepted);

    if (options.debug) {
      console.log(`[debug] query=${query}`);
      console.log(`[debug] rejected=${rejected.length}`);
      rejected.slice(0, 10).forEach((r) => console.log(`[debug] reject ${r.url} -> ${r.rejectionReason}`));
    }

    runs.push({
      search,
      query,
      generatedAt: new Date().toISOString(),
      collected: collected.length,
      duplicatesRemoved,
      accepted,
      rejected
    });
  }

  await writeOutputs(config, runs, options.dryRun);
  console.log(options.dryRun ? '[info] Dry-run complete (no files written).' : '[info] Done. Reports generated.');
};

main().catch((error) => {
  console.error('[error]', error);
  process.exitCode = 1;
});
