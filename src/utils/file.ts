import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

export interface WriteIfChangedResult {
  changed: boolean;
  path: string;
}

export const writeFileIfChanged = async (
  path: string,
  content: string
): Promise<WriteIfChangedResult> => {
  let existing: string | null = null;
  try {
    existing = await readFile(path, 'utf8');
  } catch {
    existing = null;
  }

  if (existing === content) {
    return { changed: false, path };
  }

  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content, 'utf8');
  return { changed: true, path };
};
