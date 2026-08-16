import { ContentChunk } from '@/domain/content-chunk.entity';
import { EnhancementConfig } from '@/infrastructure/config/config-schemas';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { ErrorWithDetails } from '@/utils/error-with-details';
import { Result } from '@/utils/result';
import { Injectable } from '@nestjs/common';
import { ImportanceScoringService } from './importance-scoring.service';
import { TagExtractionService } from './tag-extraction.service';

/**
 * Enhancement pipeline service — orchestrates enhancement stages after Mastra chunking.
 *
 * For each Chunk, applies:
 * 1. Importance scoring (ImportanceScoringService)
 * 2. Tag extraction (TagExtractionService)
 * 3. Memory bank assignment (from source config)
 *
 * Each stage is resilient: on error, logs and uses safe defaults, continues processing.
 * No character limit logic — that's handled upstream by Mastra config.
 */
@Injectable()
export class EnhancementPipelineService {
  constructor(
    private readonly importanceScoringService: ImportanceScoringService,
    private readonly tagExtractionService: TagExtractionService,
    private readonly logger: BasePinoLogger,
  ) {}

  /**
   * Enhance a batch of chunks by running all enhancement stages.
   *
   * @param chunks - Raw chunks from Mastra chunking
   * @param sourceId - Watch source identifier for logging context
   * @param memoryBank - Memory bank to assign to all enhanced chunks
   * @param config - Enhancement configuration from ConfigurationService
   * @returns Result.ok(enhancedChunks) or Result.ko if all chunks fail validation
   */
  async enhance(
    chunks: ContentChunk[],
    sourceId: string,
    memoryBank: string,
    config: EnhancementConfig,
  ): Promise<Result<ContentChunk[]>> {
    if (chunks.length === 0) {
      return Result.ok([]);
    }

    const enhancedChunks: ContentChunk[] = [];
    let allFailed = true;

    for (const chunk of chunks) {
      const enhancedResult = await this.enhanceChunk(chunk, sourceId, memoryBank, config);

      if (enhancedResult.isOk()) {
        enhancedChunks.push(enhancedResult.getValue());
        allFailed = false;
      } else {
        this.logger.error(
          `Chunk enhancement failed entirely for chunk; chunkId=${chunk.id}, sourceId=${sourceId}`,
          { chunkId: chunk.id, sourceId, error: enhancedResult.getFormattedErrors() },
        );
      }
    }

    if (allFailed) {
      return Result.ko([
        new ErrorWithDetails('All chunks failed enhancement validation', 'EnhancementValidationFailed'),
      ]);
    }

    return Result.ok(enhancedChunks);
  }

  /**
   * Enhance a single chunk through all stages.
   * Each stage is wrapped in try/catch for resilience.
   */
  private async enhanceChunk(
    chunk: ContentChunk,
    sourceId: string,
    memoryBank: string,
    config: EnhancementConfig,
  ): Promise<Result<ContentChunk>> {
    // Stage 1: Importance scoring
    let importance: number;
    try {
      importance = this.importanceScoringService.score(chunk, config);
    } catch (error) {
      this.logger.error(
        `Enhancement pipeline stage "importance scoring" failed; using default 0.5; chunkId=${chunk.id}, sourceId=${sourceId}`,
        {
          chunkId: chunk.id,
          sourceId,
          error: error instanceof Error ? error.message : String(error),
        },
      );
      importance = 0.5;
    }

    // Stage 2: Tag extraction
    let tags: string[];
    try {
      tags = this.tagExtractionService.extract(chunk, config);
    } catch (error) {
      this.logger.error(
        `Enhancement pipeline stage "tag extraction" failed; using empty tags; chunkId=${chunk.id}, sourceId=${sourceId}`,
        {
          chunkId: chunk.id,
          sourceId,
          error: error instanceof Error ? error.message : String(error),
        },
      );
      tags = [];
    }

    // Stage 3: Create enhanced chunk with memory bank
    const enhancedChunkResult = ContentChunk.of({
      id: chunk.id,
      text: chunk.text,
      chunkIndex: chunk.chunkIndex,
      totalChunks: chunk.totalChunks,
      sectionHeader: chunk.sectionHeader,
      breadcrumb: chunk.breadcrumb,
      language: chunk.language,
      fileRole: chunk.fileRole,
      oversized: chunk.oversized,
      startLine: chunk.startLine,
      endLine: chunk.endLine,
      metadata: chunk.metadata,
      importance,
      tags,
      memoryBank,
    });

    return enhancedChunkResult;
  }
}
