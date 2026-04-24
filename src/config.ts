import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { AppConfig } from './types.js';

const assert = (condition: unknown, message: string): void => {
  if (!condition) throw new Error(`Invalid config: ${message}`);
};

export const loadConfig = async (configPath: string): Promise<AppConfig> => {
  const content = await readFile(resolve(configPath), 'utf8');
  const parsed = JSON.parse(content) as AppConfig;

  assert(parsed.output?.reportsDir, 'output.reportsDir is required');
  assert(parsed.output?.indexFile, 'output.indexFile is required');
  assert(parsed.output?.jsonDir, 'output.jsonDir is required');
  assert(Array.isArray(parsed.searches) && parsed.searches.length > 0, 'searches is required');

  for (const search of parsed.searches) {
    assert(search.id, 'search.id is required');
    assert(search.title, `search.title is required for ${search.id}`);
    assert(search.filename, `search.filename is required for ${search.id}`);
    assert(Array.isArray(search.sites) && search.sites.length > 0, `search.sites invalid for ${search.id}`);
    assert(Number.isInteger(search.maxResults) && search.maxResults > 0, `search.maxResults invalid for ${search.id}`);
  }

  return parsed;
};
