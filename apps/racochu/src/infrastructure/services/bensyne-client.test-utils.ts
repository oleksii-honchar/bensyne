/**
 * Test utilities for BensyneClient.
 * Provides mock implementations for testing without real MCP server.
 */

import { Result } from '../../utils/result';
import { FileChunksInfo, StoredChunkInfo } from './bensyne-client.service';

/**
 * Raw snake_case chunk entry as returned by bensyne's getFileChunks tool.
 */
export interface RawStoredChunkResponse {
  chunk_index: number;
  content_hash: string;
  memory_id?: string;
  memory_status: 'present' | 'missing';
}

/**
 * Builder for a raw snake_case stored-chunk entry (getFileChunks response).
 */
export function aRawStoredChunk(
  overrides: Partial<RawStoredChunkResponse> = {},
): RawStoredChunkResponse {
  return {
    chunk_index: 0,
    content_hash: 'a'.repeat(64),
    memory_id: 'mem-1',
    memory_status: 'present',
    ...overrides,
  };
}

/**
 * Builder for a typed StoredChunkInfo (post-parse camelCase shape).
 */
export function aStoredChunkInfo(overrides: Partial<StoredChunkInfo> = {}): StoredChunkInfo {
  return {
    chunkIndex: 0,
    contentHash: 'a'.repeat(64),
    memoryId: 'mem-1',
    memoryStatus: 'present',
    ...overrides,
  };
}

/**
 * Builder for a typed FileChunksInfo (post-parse camelCase shape).
 */
export function aFileChunksInfo(overrides: Partial<FileChunksInfo> = {}): FileChunksInfo {
  return {
    status: 'present',
    fileId: 'file-1',
    fileHash: 'f'.repeat(64),
    totalChunks: 1,
    chunks: [aStoredChunkInfo()],
    ...overrides,
  };
}

/**
 * Wraps a getFileChunks payload in the MCP TextContent envelope the client
 * unwraps via parseMcpResponse.
 */
export function aGetFileChunksToolResponse(payload: Record<string, unknown>): {
  result: { content: [{ type: 'text'; text: string }] };
  _sessionId: null;
} {
  return {
    result: { content: [{ type: 'text', text: JSON.stringify(payload) }] },
    _sessionId: null,
  };
}

/**
 * Returns a stub BensyneClient that resolves all calls successfully by default.
 */
export function aBensyneClientService() {
  return {
    initialize: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    remember: jest.fn().mockResolvedValue(Result.ok({ memory_id: 'mock-memory-id', status: 'stored' })),
    forget: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    forgetByFile: jest
      .fn()
      .mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'mock-file-id', files_affected: 1 } as never),
      ),
    getFileChunks: jest.fn().mockResolvedValue(Result.ok(aFileChunksInfo())),
    registerBank: jest.fn().mockResolvedValue(Result.ok(undefined as unknown as void)),
    healthCheck: jest.fn().mockResolvedValue(Result.ok(true)),
    close: jest.fn().mockResolvedValue(undefined),
  };
}
