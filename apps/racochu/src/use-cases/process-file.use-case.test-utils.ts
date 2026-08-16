/**
 * Test utilities for ProcessFileUseCase.
 * Provides mock implementations for testing without real file processing.
 */

import { Result } from '../utils/result';

export interface ProcessFileUseCaseMock {
  execute: jest.MockedFunction<(params: unknown) => Promise<Result<unknown>>>;
}

/**
 * Returns a stub ProcessFileUseCase that resolves all calls successfully by default.
 */
export function aProcessFileUseCase(): ProcessFileUseCaseMock {
  return {
    execute: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
  };
}
