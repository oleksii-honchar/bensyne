/**
 * Test utilities for FileProcessingQueue.
 * Provides mock implementations for testing without real queue processing.
 */

/**
 * Returns a stub FileProcessingQueue that resolves all calls immediately.
 */
export function aFileProcessingQueueService() {
  return {
    addToQueue: jest.fn().mockResolvedValue(undefined),
    length: 0,
    isProcessing: jest.fn().mockReturnValue(false),
    waitForEmpty: jest.fn().mockResolvedValue(undefined),
  };
}
