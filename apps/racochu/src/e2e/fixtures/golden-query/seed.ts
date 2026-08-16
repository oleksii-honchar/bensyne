/**
 * Golden-query seed file loader — reads actual seed files from the
 * `seed-files/` directory so the content is self-documenting and
 * reviewable as standalone files (no JSON-in-TypeScript encoding).
 *
 * The seed files are copied to the watch directory before running
 * golden queries so the harness has embedded content to retrieve against.
 */

import * as fs from 'fs/promises';
import * as path from 'path';

const SEED_FILES_DIR = path.resolve(__dirname, 'seed-files');

export interface SeedFile {
  /** File path relative to watch directory (e.g. 'prose/embedding-decision.md') */
  path: string;
  /** File content read from disk */
  content: string;
}

/**
 * Recursively reads all files under `seed-files/` and returns them as
 * SeedFile entries with their relative path preserved.
 */
export async function loadGoldenQuerySeedFiles(): Promise<SeedFile[]> {
  const files = await findFiles(SEED_FILES_DIR);
  const seeds: SeedFile[] = [];

  for (const filePath of files) {
    const relPath = path.relative(SEED_FILES_DIR, filePath);
    const content = await fs.readFile(filePath, 'utf8');
    seeds.push({ path: relPath, content });
  }

  return seeds;
}

/** Recursively finds all files under a directory. */
async function findFiles(dir: string): Promise<string[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await findFiles(fullPath)));
    } else {
      files.push(fullPath);
    }
  }

  return files;
}
