import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { validateConfig } from './validate-config.js';
import type { SearchesConfig } from '../types/config.js';

export const loadConfig = async (configPath: string): Promise<SearchesConfig> => {
  const absolutePath = resolve(configPath);
  const contents = await readFile(absolutePath, 'utf8');
  const parsed = JSON.parse(contents) as unknown;
  return validateConfig(parsed);
};
