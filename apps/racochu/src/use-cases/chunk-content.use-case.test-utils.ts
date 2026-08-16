/**
 * Test utilities for ChunkContentUseCase.
 * Provides mock implementations for testing without real chunking.
 */

import { Result } from '../utils/result';

export interface ChunkContentUseCaseMock {
  execute: jest.MockedFunction<(params: unknown) => Promise<Result<unknown>>>;
}

/**
 * Returns a stub ChunkContentUseCase that resolves all calls successfully by default.
 */
export function aChunkContentUseCase(): ChunkContentUseCaseMock {
  return {
    execute: jest.fn().mockResolvedValue(Result.ok([])),
  };
}
