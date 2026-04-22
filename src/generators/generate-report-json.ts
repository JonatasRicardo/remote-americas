import type { SearchRunOutput } from '../types/result.js';

export const generateReportJson = (run: SearchRunOutput): string =>
  JSON.stringify(
    {
      metadata: {
        id: run.definition.id,
        title: run.definition.title,
        filename: run.definition.filename,
        generatedAt: run.generatedAt
      },
      query: run.query,
      stats: run.stats,
      acceptedResults: run.accepted
    },
    null,
    2
  );
