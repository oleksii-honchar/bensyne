/**
 * Shared test utilities used across multiple test files.
 *
 * Purpose: centralize duplicated mock factories and helpers so tests
 * import from one place instead of copying the same boilerplate.
 */

import * as fs from 'fs';
import type { NonSharedBuffer } from 'node:buffer';

/**
 * Creates a mock Dirent compatible with fs/promises readdir.
 *
 * Use for tests that mock directory listing without real filesystem.
 *
 * @param name - Entry name (file or directory)
 * @param isDir - Whether this entry is a directory
 * @returns Mock Dirent object
 */
export const mockDirent = (name: string, isDir: boolean): fs.Dirent<NonSharedBuffer> => ({
  name: name as unknown as NonSharedBuffer,
  parentPath: null as unknown as string,
  isDirectory: () => isDir,
  isFile: () => !isDir,
  isBlockDevice: () => false,
  isCharacterDevice: () => false,
  isSymbolicLink: () => false,
  isFIFO: () => false,
  isSocket: () => false,
});

/**
 * Creates a mock fs.Stats representing a directory.
 */
export const mockDirStats = (): fs.Stats => ({
  isDirectory: () => true,
  isFile: () => false,
  isBlockDevice: () => false,
  isCharacterDevice: () => false,
  isSymbolicLink: () => false,
  isFIFO: () => false,
  isSocket: () => false,
  dev: 0,
  ino: 0,
  mode: 16877,
  nlink: 1,
  uid: 0,
  gid: 0,
  rdev: 0,
  size: 4096,
  blksize: 4096,
  blocks: 0,
  atimeMs: 0,
  mtimeMs: 0,
  ctimeMs: 0,
  birthtimeMs: 0,
  atime: new Date(0),
  mtime: new Date(0),
  ctime: new Date(0),
  birthtime: new Date(0),
  atimeInstant: undefined as unknown,
  mtimeInstant: undefined as unknown,
  ctimeInstant: undefined as unknown,
  birthtimeInstant: undefined as unknown,
});

/**
 * Creates a mock fs.Stats representing a file.
 */
export const mockFileStats = (): fs.Stats => ({
  isDirectory: () => false,
  isFile: () => true,
  isBlockDevice: () => false,
  isCharacterDevice: () => false,
  isSymbolicLink: () => false,
  isFIFO: () => false,
  isSocket: () => false,
  dev: 0,
  ino: 0,
  mode: 33188,
  nlink: 1,
  uid: 0,
  gid: 0,
  rdev: 0,
  size: 1024,
  blksize: 4096,
  blocks: 8,
  atimeMs: 0,
  mtimeMs: 0,
  ctimeMs: 0,
  birthtimeMs: 0,
  atime: new Date(0),
  mtime: new Date(0),
  ctime: new Date(0),
  birthtime: new Date(0),
  atimeInstant: undefined as unknown,
  mtimeInstant: undefined as unknown,
  ctimeInstant: undefined as unknown,
  birthtimeInstant: undefined as unknown,
});
