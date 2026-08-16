/**
 * Test utilities for BensyneClient.
 * Provides mock implementations for testing without real MCP server.
 */

import { Result } from '../../utils/result';

/**
 * Returns a stub BensyneClient that resolves all calls successfully by default.
 */
export function aBensyneClientService() {
  return {
    initialize: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    remember: jest.fn().mockResolvedValue(Result.ok({ memory_id: 'mock-memory-id', status: 'stored' })),
    forget: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    registerBank: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    healthCheck: jest.fn().mockResolvedValue(Result.ok(true)),
    close: jest.fn().mockResolvedValue(undefined),
  };
}
