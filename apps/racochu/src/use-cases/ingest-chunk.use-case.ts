import { Injectable } from '@nestjs/common';
import { z } from 'zod';
import { ContentChunk } from '../domain/content-chunk.entity';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { BaseUseCase } from '../utils/base-use-case';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';

const ingestChunkParamsSchema = z.object({
  chunks: z.array(z.custom<ContentChunk>()),
  sourceId: z.string().min(1),
  metadata: z.record(z.string(), z.string()).optional(),
  fileHash: z.string().optional(),
  hardwareId: z.string().optional(),
});

export type IngestChunkParams = z.infer<typeof ingestChunkParamsSchema>;

@Injectable()
export class IngestChunkUseCase extends BaseUseCase<IngestChunkParams, void> {
  constructor(
    private readonly bensyneClient: BensyneClient,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    logger: BasePinoLogger,
  ) {
    super(logger);
    this.logger = this.logger.child({ component: 'IngestChunkUseCase' });
  }

  protected validateParams(params: IngestChunkParams): Result<IngestChunkParams> {
    const parsed = ingestChunkParamsSchema.safeParse(params);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails(
          'Invalid ingest chunk params: ' + parsed.error.message,
          'InvalidIngestChunkParams',
        ),
      ]);
    }
    return Result.ok(parsed.data);
  }

  protected async executeInternal(params: IngestChunkParams): Promise<Result<void>> {
    this.logger.debug(`Ingesting chunks; count=${params.chunks.length}, source="${params.sourceId}"`);

    if (params.chunks.length === 0) {
      this.logger.debug('No chunks to ingest');
      return Result.ok(undefined as unknown as void);
    }

    let successCount = 0;
    let failureCount = 0;
    const errors: { chunkId: bigint; error: string }[] = [];

    for (const chunk of params.chunks) {
      try {
        const result = await this.bensyneClient.remember(chunk);
        if (result.isOk()) {
          const { memory_id, status } = result.getValue();
          successCount++;
          this.logger.debug(
            `Chunk ingested; id="${chunk.id}", index=${chunk.chunkIndex}, memoryId="${memory_id}", status="${status}"`,
          );

          // Track memory mapping (non-fatal)
          const filePath = params.metadata?.filePath;
          if (filePath) {
            try {
              await this.fileMemoryTrackerService.trackMemory(
                filePath,
                memory_id,
                params.sourceId,
                chunk.memoryBank,
                params.fileHash,
                params.hardwareId,
              );
            } catch (error) {
              this.logger.warn(
                `Failed to track memory; filePath="${filePath}", memoryId="${memory_id}", error="${error instanceof Error ? error.message : String(error)}"`,
              );
            }
          }
        } else {
          failureCount++;
          errors.push({
            chunkId: chunk.id,
            error: result.getFormattedErrors(),
          });
          this.logger.error(
            `Chunk ingestion failed; id="${chunk.id}", error="${result.getFormattedErrors()}"`,
          );
        }
      } catch (error) {
        failureCount++;
        errors.push({
          chunkId: chunk.id,
          error: error instanceof Error ? error.message : String(error),
        });
        this.logger.error(
          `Chunk ingestion threw: id="${chunk.id}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }

    this.logger.info(
      `Chunk ingestion completed: source="${params.sourceId}", total=${params.chunks.length}, success=${successCount}, failed=${failureCount}`,
    );

    if (failureCount > 0 && successCount === 0) {
      return Result.ko([
        new ErrorWithDetails(
          `Failed to ingest all ${failureCount} chunks: ${errors.map(e => e.error).join('; ')}`,
          'IngestionFailed',
        ),
      ]);
    }

    if (failureCount > 0) {
      this.logger.warn(
        `Partial chunk ingestion: ${failureCount}/${params.chunks.length} failed: ${errors.map(e => `${e.chunkId}(${e.error})`).join('; ')}`,
      );
    }

    return Result.ok(undefined as unknown as void);
  }
}
