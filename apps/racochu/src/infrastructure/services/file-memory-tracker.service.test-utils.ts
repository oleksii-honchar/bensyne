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
    // Ingest-gate reads default to the UNTRACKED shape (no stored hash) so the
    // hash-gate never fires unless a test opts in — existing flows stay
    // ungated by default (fail-open defaults, spec C3).
    getIngestGateState: jest.fn().mockResolvedValue({ storedHash: null, skipReason: null, tracked: false }),
    recordTerminalSkip: jest.fn().mockResolvedValue(undefined),
    findBySourceId: jest.fn().mockResolvedValue([]),
    findExpiredBySourceId: jest.fn().mockResolvedValue([]),
    getTrackerCreatedAt: jest.fn().mockResolvedValue(null),
    deleteByFilePath: jest.fn().mockResolvedValue(undefined),
  };
}
