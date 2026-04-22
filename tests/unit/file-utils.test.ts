import { mkdtemp, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { describe, expect, it } from 'vitest';
import { writeFileIfChanged } from '../../src/utils/file.js';

describe('writeFileIfChanged', () => {
  it('avoids rewriting unchanged content', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'job-search-'));
    const file = join(dir, 'out.md');

    const first = await writeFileIfChanged(file, 'hello');
    const second = await writeFileIfChanged(file, 'hello');
    const current = await readFile(file, 'utf8');

    expect(first.changed).toBe(true);
    expect(second.changed).toBe(false);
    expect(current).toBe('hello');
  });
});
