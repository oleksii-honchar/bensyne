import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';

/**
 * Absolute path to e2e fixtures directory.
 */
export const FIXTURES_DIR = path.resolve(__dirname, 'fixtures');

/**
 * Creates a temporary directory for e2e test files.
 * Directory is NOT auto-cleaned — call cleanupTempDir when done.
 */
export async function createTempDir(prefix = 'rag-e2e-'): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), prefix));
}

/**
 * Cleans up a temporary directory created by createTempDir.
 */
export async function cleanupTempDir(dirPath: string): Promise<void> {
  try {
    await fs.rm(dirPath, { recursive: true, force: true });
  } catch {
    // Ignore cleanup errors
  }
}

/**
 * Reads content from a fixture file by name (e.g., 'sample.md').
 */
export async function readFixture(fixtureName: string): Promise<string> {
  const fixturePath = path.join(FIXTURES_DIR, fixtureName);
  return fs.readFile(fixturePath, 'utf-8');
}
