/**
 * Shared chokidar mock for FileWatcherService tests.
 *
 * Import this file at the top of test files that need a chokidar mock:
 *
 *   import './file-watcher.service.test-utils';
 *
 * Jest hoists jest.mock() calls automatically, so the import order does not
 * matter as long as this file is imported before any module under test.
 */
const mockWatcher = {
  on: jest.fn(),
  close: jest.fn().mockResolvedValue(undefined),
};

jest.mock('chokidar', () => ({
  watch: jest.fn(() => mockWatcher),
}));

export const aChokidarWatcher = (): typeof mockWatcher => mockWatcher;
