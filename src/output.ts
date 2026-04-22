import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import type { AppConfig, SearchRun } from './types.js';

const writeIfChanged = async (path: string, content: string): Promise<boolean> => {
  let current: string | undefined;
  try {
    current = await readFile(path, 'utf8');
  } catch {
    current = undefined;
  }

  if (current === content) return false;
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content, 'utf8');
  return true;
};

const markdown = (run: SearchRun): string => {
  const lines: string[] = [`# ${run.search.title}`, '', `Generated at: ${run.generatedAt}`, '', 'Query used:', `\`${run.query}\``, '', '## Results', ''];

  run.accepted.forEach((r, index) => {
    lines.push(`${index + 1}. [${r.title}](${r.url})`);
    lines.push(`   - Source: ${r.sourceDomain}`);
    lines.push(`   - Score: ${r.score}`);
    lines.push(`   - Matched: ${r.matchedIncludeTerms.join(', ') || 'none'}`);
    lines.push(`   - Summary: ${r.snippet}`);
    lines.push('');
  });

  lines.push('## Stats');
  lines.push(`- Total collected: ${run.collected}`);
  lines.push(`- Total after filtering: ${run.accepted.length}`);
  lines.push(`- Duplicates removed: ${run.duplicatesRemoved}`);
  return lines.join('\n');
};

const json = (run: SearchRun): string =>
  JSON.stringify(
    {
      metadata: {
        id: run.search.id,
        title: run.search.title,
        filename: run.search.filename,
        generatedAt: run.generatedAt
      },
      query: run.query,
      stats: {
        totalCollected: run.collected,
        totalAfterFiltering: run.accepted.length,
        duplicatesRemoved: run.duplicatesRemoved
      },
      acceptedResults: run.accepted
    },
    null,
    2
  );

const indexMarkdown = (runs: SearchRun[], generatedAt: string): string => {
  const lines = ['# Job Search Reports', '', `Last updated: ${generatedAt}`, '', '| Report | Search ID | Accepted | Collected |', '| --- | --- | ---: | ---: |'];
  runs.forEach((run) => {
    lines.push(`| [${run.search.title}](./${run.search.filename}) | ${run.search.id} | ${run.accepted.length} | ${run.collected} |`);
  });
  lines.push('');
  return lines.join('\n');
};

export const writeOutputs = async (config: AppConfig, runs: SearchRun[], dryRun: boolean): Promise<void> => {
  if (dryRun) return;

  for (const run of runs) {
    await writeIfChanged(join(config.output.reportsDir, run.search.filename), markdown(run));
    await writeIfChanged(join(config.output.jsonDir, `${run.search.id}.json`), json(run));
  }

  await writeIfChanged(config.output.indexFile, indexMarkdown(runs, new Date().toISOString()));
};
