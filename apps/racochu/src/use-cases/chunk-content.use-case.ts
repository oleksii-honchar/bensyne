import { Injectable } from '@nestjs/common';
import * as crypto from 'crypto';
import { z } from 'zod';
import { DEFAULT_CONTENT_FILTER_OPTIONS } from '../application/services/content-classifier.service';
import { EnhancementPipelineService } from '../application/services/enhancement-pipeline.service';
import { BaseChunkingStrategy } from '../application/strategies/base-chunking-strategy';
import { StrategyRouter } from '../application/strategies/strategy-router.service';
import { ContentChunk } from '../domain/content-chunk.entity';
import { watchSourceConfigSchema } from '../infrastructure/config/config-schemas';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { SOURCE_TYPES } from '../infrastructure/config/source-types';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { RememberRequestSerializer } from '../infrastructure/mnemosyne/remember-request.serializer';
import { BaseUseCase } from '../utils/base-use-case';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';

const chunkContentParamsSchema = z.object({
  content: z.string().min(1),
  filePath: z.string().min(1),
  sourceId: z.string().min(1),
  memoryBank: z.string().min(1),
  maxTokens: z.number().positive().optional(),
  overlapTokens: z.number().nonnegative().optional(),
  hardCapTokens: z.number().positive().optional(),
  sourceConfig: watchSourceConfigSchema.optional(),
  fileHash: z.string().optional(),
  hardwareId: z.string().optional(),
  skipEnrichment: z.boolean().optional(),
});

export type ChunkContentParams = z.infer<typeof chunkContentParamsSchema>;

@Injectable()
export class ChunkContentUseCase extends BaseUseCase<ChunkContentParams, ContentChunk[]> {
  private readonly serializer: RememberRequestSerializer;

  constructor(
    private readonly strategyRouter: StrategyRouter,
    private readonly enhancementPipelineService: EnhancementPipelineService,
    private readonly configurationService: ConfigurationService,
    logger: BasePinoLogger,
  ) {
    super(logger);
    this.logger = this.logger.child({ component: 'ChunkContentUseCase' });
    this.serializer = new RememberRequestSerializer();
  }

  protected validateParams(params: ChunkContentParams): Result<ChunkContentParams> {
    const parsed = chunkContentParamsSchema.safeParse(params);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails(
          'Invalid chunk content params: ' + parsed.error.message,
          'InvalidChunkContentParams',
        ),
      ]);
    }
    return Result.ok(parsed.data);
  }

  protected async executeInternal(params: ChunkContentParams): Promise<Result<ContentChunk[]>> {
    this.logger.debug(
      `Chunking content; path="${params.filePath}", length=${params.content.length}, memoryBank="${params.memoryBank}"`,
    );

    // Select chunker based on sourceConfig (defaults to vault/Mastra — D29)
    const chunker: BaseChunkingStrategy = params.sourceConfig
      ? this.strategyRouter.selectStrategy(params.sourceConfig)
      : this.strategyRouter.selectStrategy({
          id: params.sourceId,
          path: params.filePath,
          memoryBank: params.memoryBank,
          exclude: [],
          debounceMs: 3000,
          sourceType: SOURCE_TYPES.VAULT,
          contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
          autoPopulate: true,
        });

    // Guard: chunker must not be undefined (a router that degraded with no
    // fallback binding available — e.g. a broken DI container)
    if (!chunker) {
      this.logger.error(
        `No chunker selected for sourceId="${params.sourceId}", sourceConfig.sourceType="${params.sourceConfig?.sourceType}"`,
      );
      return Result.ko([
        new ErrorWithDetails(
          `No chunker selected for sourceId="${params.sourceId}"`,
          'StrategySelectionError',
        ),
      ]);
    }

    const effectiveSourceConfig = params.sourceConfig ?? {
      id: params.sourceId,
      path: params.filePath,
      memoryBank: params.memoryBank,
      exclude: [],
      debounceMs: 3000,
      sourceType: SOURCE_TYPES.VAULT,
      contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
      autoPopulate: true,
    };

    // skipEnrichment (spec §4.3, ADR-2): force the enrichment-free path so
    // recover can enumerate the expected chunk set with zero LLM cost regardless
    // of config. The override is passed as the optional 5th param of
    // chunkFile — the 4th slot stays `effectiveSourceConfig` (collision warning).
    const skipEnrichment = params.skipEnrichment === true;
    const chunksResult = skipEnrichment
      ? await chunker.chunkFile(params.content, params.filePath, params.sourceId, effectiveSourceConfig, {
          skipEnrichment: true,
        })
      : await chunker.chunkFile(params.content, params.filePath, params.sourceId, effectiveSourceConfig);

    if (chunksResult.isKo()) {
      this.logger.error(
        `Chunking failed: path="${params.filePath}", error="${chunksResult.getFormattedErrors()}"`,
      );
      return chunksResult;
    }

    const chunks = chunksResult.getValue();
    this.logger.info(`Content chunked: path="${params.filePath}", chunks=${chunks.length}`);

    // Pipe chunks through enhancement pipeline — skipped entirely on the
    // enrichment-free path (skipEnrichment) so verification costs zero LLM.
    const enhancementConfig = this.configurationService.getEnhancementConfig();
    const enhancementResult = skipEnrichment
      ? undefined
      : await this.enhancementPipelineService.enhance(
          chunks,
          params.sourceId,
          params.memoryBank,
          enhancementConfig,
        );

    // Determine final chunks (enhanced if available, raw otherwise)
    let finalChunks: ContentChunk[];
    if (enhancementResult === undefined) {
      // skipEnrichment path — raw chunks carry no enhancement
      finalChunks = chunks;
    } else if (enhancementResult.isOk()) {
      this.logger.info(
        `Chunks enhanced: path="${params.filePath}", enhanced=${enhancementResult.getValue().length}`,
      );
      finalChunks = enhancementResult.getValue();
    } else {
      // Fallback: log error and return raw chunks (resilient)
      this.logger.error(
        `Enhancement pipeline failed, returning raw chunks: path="${params.filePath}", error="${enhancementResult.getFormattedErrors()}"`,
      );
      finalChunks = chunks;
    }

    // Inject sourceType, fileHash, hardwareId, and chunkHash into chunk metadata.
    // sourceType (D29) is stamped from the originating watch source — one name
    // end-to-end: config → chunk → wire → DB. chunkHash (sha256 of the chunk's
    // exact text) is always computed; fileHash and hardwareId are injected when
    // provided. chunkHash computation is non-fatal — on failure the key is
    // omitted (mirrors the fileHash policy).
    finalChunks = finalChunks.map(chunk => {
      const existingMetadata = chunk.metadata ?? {};
      const updatedMetadata: Record<string, string> = { ...existingMetadata };
      updatedMetadata.sourceType = effectiveSourceConfig.sourceType;
      if (params.fileHash) {
        updatedMetadata.fileHash = params.fileHash;
      }
      if (params.hardwareId) {
        updatedMetadata.hardwareId = params.hardwareId;
      }
      const chunkHash = this.computeChunkHash(chunk.text);
      if (chunkHash !== undefined) {
        updatedMetadata.chunkHash = chunkHash;
      }

      const updatedProps = chunk.toJson();
      updatedProps.metadata = updatedMetadata;
      return ContentChunk.of(updatedProps).getValue();
    });

    // Clamp oversized chunks (UTF-8 byte limit for Cyrillic text).
    // Measure the serialized request body size, not just the chunk text.
    const MAX_REQUEST_BYTES = 4000; // Leave margin for metadata variations
    let allChunks: ContentChunk[] = [];
    let chunkIndex = 0;
    for (const chunk of finalChunks) {
      // Measure the actual serialized request body size
      const serialized = this.serializer.buildAndSerialize(chunk);
      const serializedBytes = Buffer.byteLength(serialized, 'utf8');

      if (serializedBytes <= MAX_REQUEST_BYTES) {
        // Chunk fits — re-index and add
        const chunkProps = chunk.toJson();
        chunkProps.chunkIndex = chunkIndex++;
        allChunks.push(ContentChunk.of(chunkProps).getValue());
      } else {
        // Re-chunk oversized chunk to stay under request body limit
        this.logger.info(
          `Clamping oversized chunk: path="${params.filePath}", originalChunkIndex=${chunk.chunkIndex}, serializedBytes=${serializedBytes}`,
        );
        const clampedChunks = this.clampChunkToRequestBody(chunk, MAX_REQUEST_BYTES);
        for (const clamped of clampedChunks) {
          const chunkProps = clamped.toJson();
          chunkProps.chunkIndex = chunkIndex++;
          allChunks.push(ContentChunk.of(chunkProps).getValue());
        }
      }
    }

    return Result.ok(allChunks);
  }

  /**
   * Computes the sha256 hex digest of a chunk's exact text as sent in `content`.
   * Non-fatal: on any error the failure is logged and undefined returned so the
   * `chunkHash` key is omitted from metadata (mirrors the fileHash policy).
   */
  private computeChunkHash(text: string): string | undefined {
    try {
      return crypto.createHash('sha256').update(text).digest('hex');
    } catch (error) {
      this.logger.error(
        `Failed to compute chunkHash: error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return undefined;
    }
  }

  /**
   * Clamps a chunk to stay under the request body limit by splitting the text
   * at safe boundaries (paragraph, sentence, or byte) and measuring each split
   * against the actual serialized request body size.
   */
  private clampChunkToRequestBody(chunk: ContentChunk, maxRequestBytes: number): ContentChunk[] {
    const text = chunk.text;

    // Use binary search to find the maximum content length that fits
    let low = 0;
    let high = text.length;

    while (low < high) {
      const mid = Math.floor((low + high + 1) / 2);
      const testContent = text.substring(0, mid);
      const testChunk = this.createClampedChunk(chunk, testContent);

      const serialized = this.serializer.buildAndSerialize(testChunk);
      const serializedBytes = Buffer.byteLength(serialized, 'utf8');

      if (serializedBytes <= maxRequestBytes) {
        low = mid;
      } else {
        high = mid - 1;
      }
    }

    // low is now the maximum character count that fits
    if (low === 0) {
      // Even 1 character is too large — return the original chunk as-is
      this.logger.warn(
        `Chunk cannot be clamped to fit request body limit: chunkIndex=${chunk.chunkIndex}`,
      );
      return [chunk];
    }

    // Split the text at the found boundary
    const fits = text.substring(0, low);
    const remainder = text.substring(low);

    const chunks: ContentChunk[] = [this.createClampedChunk(chunk, fits)];

    // If there's remainder, create a new chunk for it
    if (remainder.length > 0) {
      // Trim leading whitespace from remainder
      const trimmedRemainder = remainder.trimStart();
      if (trimmedRemainder.length > 0) {
        // Recursively clamp the remainder
        const remainderChunks = this.clampChunkToRequestBody(
          this.createClampedChunk(chunk, trimmedRemainder),
          maxRequestBytes,
        );
        chunks.push(...remainderChunks);
      }
    }

    return chunks;
  }

  private createClampedChunk(originalChunk: ContentChunk, text: string): ContentChunk {
    // Copy metadata from original chunk
    const metadata = originalChunk.metadata ? { ...originalChunk.metadata } : {};
    const chunkProps = originalChunk.toJson();
    chunkProps.text = text;
    chunkProps.metadata = metadata;
    return ContentChunk.of(chunkProps).getValue();
  }
}
