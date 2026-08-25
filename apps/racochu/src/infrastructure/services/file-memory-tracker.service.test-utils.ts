/**
 * Test utilities for FileMemoryTrackerService.
 * Provides mock implementations for testing without real tracker infrastructure.
 */

/**
 * Returns a stub FileMemoryTrackerService that resolves all calls successfully by default.
 */
export function aFileMemoryTrackerService() {
  return {
    trackMemory: jest.fn().mockResolvedValue(undefined),
    forgetMemory: jest.fn().mockResolvedValue(null),
    forgetMemories: jest.fn().mockResolvedValue(null),
    getMemoryIds: jest.fn().mockResolvedValue([]),
    findBySourceId: jest.fn().mockResolvedValue([]),
    findExpiredBySourceId: jest.fn().mockResolvedValue([]),
    getTrackerCreatedAt: jest.fn().mockResolvedValue(null),
    deleteByFilePath: jest.fn().mockResolvedValue(undefined),
  };
}
