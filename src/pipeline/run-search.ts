import { join } from 'node:path';
import type { SearchDefinition } from '../types/config.js';
import type { SearchProvider } from '../search/provider.js';
import type { SearchRunOutput } from '../types/result.js';
import { buildQuery } from '../query/build-query.js';
import { normalizeResult } from '../normalize/normalize-result.js';
import { dedupeResults } from '../filters/dedupe-results.js';
import { filterResults } from '../filters/filter-results.js';
import { generateReportMarkdown } from '../generators/generate-report-markdown.js';
import { generateReportJson } from '../generators/generate-report-json.js';
import { writeFileIfChanged } from '../utils/file.js';
import { nowIso } from '../utils/time.js';
import { Logger } from '../utils/logger.js';

export interface RunSearchOptions {
  dryRun?: boolean;
  debug?: boolean;
  reportsDir: string;
  jsonDir: string;
}

export const runSearch = async (
  definition: SearchDefinition,
  provider: SearchProvider,
  options: RunSearchOptions,
  logger: Logger
): Promise<SearchRunOutput> => {
  const generatedAt = nowIso();
  const { query } = buildQuery(definition);

  logger.info('Running search', { id: definition.id, provider: provider.name });
  const rawResults = await provider.search(query, definition);
  const normalized = rawResults.map(normalizeResult);

  const { unique, duplicates } = dedupeResults(normalized);
  const { accepted, rejected } = filterResults(unique, definition, options.debug);

  const output: SearchRunOutput = {
    definition,
    query,
    generatedAt,
    stats: {
      totalCollected: rawResults.length,
      duplicatesRemoved: duplicates.length,
      totalAfterFiltering: accepted.length
    },
    accepted: accepted.sort((a, b) => b.score - a.score).slice(0, definition.maxResults),
    rejected: [...duplicates, ...rejected]
  };

  const markdown = generateReportMarkdown(output);
  const json = generateReportJson(output);

  if (!options.dryRun) {
    await writeFileIfChanged(join(options.reportsDir, definition.filename), markdown);
    await writeFileIfChanged(join(options.jsonDir, `${definition.id}.json`), json);
  }

  if (options.debug) {
    logger.debug('Search debug summary', {
      id: definition.id,
      rejectedReasons: output.rejected.map((item) => item.rejectionReason ?? 'unknown')
    });
  }

  return output;
};
