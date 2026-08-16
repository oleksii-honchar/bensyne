import { ContentChunk } from '@/domain/content-chunk.entity';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { Inject, Injectable } from '@nestjs/common';

/** Injection token for BensyneFileClient. */
export const BENSYNE_FILE_CLIENT = 'BensyneFileClient';

/**
 * Interface for communicating with bensyne's FileService.
 *
 * Abstracts the transport layer (HTTP, MCP, etc.) so the propagator
 * can be tested in isolation and swapped with different clients.
 */
export interface BensyneFileClient {
  /**
   * Upsert a file entity in bensyne.
   *
   * @param fileData - File metadata to create or update
   * @returns Result.ok with the file entity on success
   */
  upsertFile(fileData: FileUpsertData): Promise<Result<FileUpsertResult>>;

  /**
   * Create a file-chunk link in bensyne.
   *
   * @param chunkData - Chunk linkage data
   * @returns Result.ok with the chunk entity on success
   */
  createChunk(chunkData: FileChunkData): Promise<Result<FileChunkResult>>;
}

/** File data sent to bensyne for upsert. */
export interface FileUpsertData {
  id?: string;
  path: string;
  source_type: string;
  hash?: string;
  file_type?: string;
  size?: number;
  language?: string;
  aggregated_keywords?: string[];
  aggregated_tags?: string[];
}

/** Upsert result from bensyne. */
export interface FileUpsertResult {
  id: string;
  path: string;
}

/** Chunk linkage data sent to bensyne. */
export interface FileChunkData {
  file_id: string;
  memory_id: string;
  chunk_index: number;
  start_line?: number;
  end_line?: number;
}

/** Chunk result from bensyne. */
export interface FileChunkResult {
  id: string;
}

/**
 * Propagation result returned to the caller.
 */
export interface PropagationResult {
  file_id: string;
  chunk_id: string;
}

/**
 * Maps racochu source identifiers to bensyne SourceType values.
 */
const SOURCE_TYPE_MAP: Record<string, string> = {
  file_system: 'file_system',
  agent_session: 'agent_session',
  git: 'git',
  database: 'database',
  external: 'external',
  remote: 'remote',
};

/**
 * FileMetadataPropagator — propagates file metadata from racochu ContentChunk
 * to bensyne's FileService during the enhancement pipeline.
 *
 * Extracts file path, source type, language, and tags from the chunk,
 * upserts the file in bensyne, then creates a file-chunk link.
 *
 * Propagation failure is non-fatal: returns Result.ko without throwing,
 * allowing the enhancement pipeline to continue.
 */
@Injectable()
export class FileMetadataPropagator {
  constructor(
    @Inject(BENSYNE_FILE_CLIENT) private readonly bensyneClient: BensyneFileClient,
    private readonly logger: BasePinoLogger,
  ) {}

  /**
   * Propagate file metadata from a ContentChunk to bensyne.
   *
   * Extracts file metadata from the chunk (path, source_type, language, tags),
   * upserts the file in bensyne, and creates a file-chunk link to the memory.
   *
   * @param chunk - The ContentChunk containing file metadata
   * @param memoryId - The memory ID returned by bensyne after storing the chunk
   * @returns Result.ok with { file_id, chunk_id } on success; Result.ko on error
   */
  async propagateFileMetadata(chunk: ContentChunk, memoryId: string): Promise<Result<PropagationResult>> {
    try {
      // Extract file path: prefer metadata.filePath, fall back to breadcrumb
      const filePath = this.extractFilePath(chunk);
      if (!filePath) {
        return Result.ko([
          new ErrorWithDetails('No file path found in chunk metadata or breadcrumb', 'MissingFilePath'),
        ]);
      }

      // Extract source type from chunk metadata
      const sourceType = this.extractSourceType(chunk);

      // Build file upsert data
      const fileData: FileUpsertData = {
        path: filePath,
        source_type: sourceType,
        language: chunk.language,
        aggregated_tags: [...chunk.tags],
      };

      // Upsert file in bensyne
      const upsertResult = await this.bensyneClient.upsertFile(fileData);
      if (upsertResult.isKo()) {
        this.logger.error(`Failed to upsert file in bensyne: ${upsertResult.getFormattedErrors()}`, {
          filePath,
          sourceType,
        });
        return Result.ko(upsertResult.getErrors());
      }

      const fileResult = upsertResult.getValue();

      // Build chunk linkage data
      const chunkData: FileChunkData = {
        file_id: fileResult.id,
        memory_id: memoryId,
        chunk_index: chunk.chunkIndex,
        start_line: chunk.startLine,
        end_line: chunk.endLine,
      };

      // Create file-chunk link
      const createChunkResult = await this.bensyneClient.createChunk(chunkData);
      if (createChunkResult.isKo()) {
        this.logger.error(
          `Failed to create file chunk link in bensyne: ${createChunkResult.getFormattedErrors()}`,
          { file_id: fileResult.id, memoryId },
        );
        return Result.ko(createChunkResult.getErrors());
      }

      const chunkResult = createChunkResult.getValue();

      this.logger.debug(`File metadata propagated: file_id=${fileResult.id}, chunk_id=${chunkResult.id}`, {
        file_id: fileResult.id,
        chunk_id: chunkResult.id,
        filePath,
      });

      return Result.ok({
        file_id: fileResult.id,
        chunk_id: chunkResult.id,
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error(`Exception during file metadata propagation: ${errorMessage}`, {
        error: errorMessage,
      });
      return Result.ko([new ErrorWithDetails(errorMessage, 'PropagationException')]);
    }
  }

  /**
   * Extract file path from chunk: prefer metadata.filePath, fall back to breadcrumb.
   */
  private extractFilePath(chunk: ContentChunk): string | null {
    const fromMetadata = chunk.metadata?.filePath;
    if (fromMetadata) {
      return fromMetadata;
    }
    const fromBreadcrumb = chunk.breadcrumb;
    if (fromBreadcrumb) {
      return fromBreadcrumb;
    }
    return null;
  }

  /**
   * Extract source type from chunk metadata.sourceId, defaulting to 'unknown'.
   */
  private extractSourceType(chunk: ContentChunk): string {
    const sourceId = chunk.metadata?.sourceId;
    if (!sourceId) {
      return 'unknown';
    }
    return SOURCE_TYPE_MAP[sourceId] ?? 'unknown';
  }
}
