import type { SearchRunOutput } from '../types/result.js';

export const generateReportMarkdown = (run: SearchRunOutput): string => {
  const lines: string[] = [];
  lines.push(`# ${run.definition.title}`);
  lines.push('');
  lines.push(`Generated at: ${run.generatedAt}`);
  lines.push('');
  lines.push('Query used:');
  lines.push(`\`${run.query}\``);
  lines.push('');
  lines.push('## Results');
  lines.push('');

  if (run.accepted.length === 0) {
    lines.push('No accepted results found.');
  } else {
    run.accepted.forEach((result, index) => {
      const matched = [...result.matchedIncludeTerms];
      lines.push(`${index + 1}. [${result.title}](${result.url})`);
      lines.push(`   - Source: ${result.sourceDomain}`);
      lines.push(`   - Score: ${result.score}`);
      lines.push(`   - Matched: ${matched.join(', ') || 'none'}`);
      lines.push(`   - Summary: ${result.snippet}`);
      lines.push('');
    });
  }

  lines.push('## Stats');
  lines.push(`- Total collected: ${run.stats.totalCollected}`);
  lines.push(`- Total after filtering: ${run.stats.totalAfterFiltering}`);
  lines.push(`- Duplicates removed: ${run.stats.duplicatesRemoved}`);

  return lines.join('\n');
};
