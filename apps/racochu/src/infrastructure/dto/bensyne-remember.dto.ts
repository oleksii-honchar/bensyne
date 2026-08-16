import { ContentChunk } from '../../domain/content-chunk.entity';

/**
 * Payload shape for the memory_remember MCP tool call arguments.
 * Maps domain Chunk entity properties to the MCP request format.
 */
export interface MnemosyneRememberPayload {
  content: string;
  memory_bank: string;
  importance: number;
  source: string;
  metadata: {
    id: bigint;
    chunkIndex: number;
    totalChunks: number;
    sectionHeader: string;
    breadcrumb: string;
    fileRole: string;
    language?: string;
    startLine?: number;
    endLine?: number;
    importance: number;
    tags: string[];
    memoryBank: string;
    [key: string]: unknown;
  };
}

/**
 * DTO for transforming a Chunk domain entity into the Mnemosyne remember payload.
 * Encapsulates the mapping logic so BensyneClient stays focused on transport.
 */
export class BensyneRememberDto {
  static fromChunk(chunk: ContentChunk): MnemosyneRememberPayload {
    return {
      content: chunk.text,
      memory_bank: chunk.memoryBank,
      importance: chunk.importance,
      source: chunk.memoryBank,
      metadata: {
        id: chunk.id,
        chunkIndex: chunk.chunkIndex,
        totalChunks: chunk.totalChunks,
        sectionHeader: chunk.sectionHeader,
        breadcrumb: chunk.breadcrumb,
        fileRole: chunk.fileRole,
        ...(chunk.language !== undefined && { language: chunk.language }),
        ...(chunk.startLine !== undefined && { startLine: chunk.startLine }),
        ...(chunk.endLine !== undefined && { endLine: chunk.endLine }),
        importance: chunk.importance,
        tags: chunk.tags,
        memoryBank: chunk.memoryBank,
        ...(chunk.metadata || {}),
      },
    };
  }
}
