/**
 * Test utilities for IngestChunkUseCase.
 * Provides mock implementations for testing without real ingestion.
 */

import { Result } from '../utils/result';

export interface IngestChunkUseCaseMock {
  execute: jest.MockedFunction<(params: unknown) => Promise<Result<unknown>>>;
}

/**
 * Returns a stub IngestChunkUseCase that resolves all calls successfully by default.
 */
export function aIngestChunkUseCase(): IngestChunkUseCaseMock {
  return {
    execute: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
  };
}
