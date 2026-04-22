import { Ajv2020 } from 'ajv/dist/2020.js';
import type { ErrorObject } from 'ajv';
import schema from '../../searches.schema.json' with { type: 'json' };
import type { SearchesConfig } from '../types/config.js';

const ajv = new Ajv2020({ allErrors: true });
const validator = ajv.compile<SearchesConfig>(schema);

export const validateConfig = (config: unknown): SearchesConfig => {
  if (!validator(config)) {
    const errors = (validator.errors ?? [])
      .map((error: ErrorObject) => `${error.instancePath || '/'} ${error.message ?? 'invalid'}`)
      .join('; ');
    throw new Error(`Invalid config: ${errors}`);
  }
  return config as SearchesConfig;
};
