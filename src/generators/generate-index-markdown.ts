import type { SearchRunOutput } from '../types/result.js';

export const generateIndexMarkdown = (runs: SearchRunOutput[], generatedAt: string): string => {
  const lines: string[] = [];
  lines.push('# Job Search Reports');
  lines.push('');
  lines.push(`Last updated: ${generatedAt}`);
  lines.push('');
  lines.push('| Report | Search ID | Accepted | Collected |');
  lines.push('| --- | --- | ---: | ---: |');
  for (const run of runs) {
    lines.push(
      `| [${run.definition.title}](./${run.definition.filename}) | ${run.definition.id} | ${run.stats.totalAfterFiltering} | ${run.stats.totalCollected} |`
    );
  }
  lines.push('');
  return lines.join('\n');
};
