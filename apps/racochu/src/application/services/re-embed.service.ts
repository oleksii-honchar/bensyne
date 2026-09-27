import { Injectable } from '@nestjs/common';
import { FileTracker } from '../../domain/file-tracker.aggregate';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { FileTrackerRepository } from '../../infrastructure/repositories/file-tracker.repository';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileHasherService } from '../../infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { HardwareIdDetectorService } from '../../infrastructure/services/hardware-id-detector.service';
import { ChunkContentUseCase } from '../../use-cases/chunk-content.use-case';
import { IngestChunkUseCase } from '../../use-cases/ingest-chunk.use-case';
import { ProcessFileUseCase } from '../../use-cases/process-file.use-case';

/**
 * Outcome of the per-file re-embed decision.
 */
export type ReEmbedOutcome =
  | { status: 'skipped-healthy' }
  | { status: 're-embedded'; chunks: number }
  | { status: 'dry-run'; wouldReembed: number }
  | { status: 'error'; reason: string };

export interface ReEmbedOptions {
  dryRun?: boolean;
}

/**
 * Re-embeds files with missing embeddings.
 *
 * Checks each tracked file's chunks for missing `memory_status` (embedding) and
 * re-processes only those files. Files with all chunks already embedded are skipped.
 */
@Injectable()
export class ReEmbedService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly fileTrackerRepository: FileTrackerRepository,
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly chunkContentUseCase: ChunkContentUseCase,
    private readonly ingestChunkUseCase: IngestChunkUseCase,
    private readonly bensyneClient: BensyneClient,
    private readonly fileHasherService: FileHasherService,
    private readonly hardwareIdDetectorService: HardwareIdDetectorService,
    private readonly processingQueue: FileProcessingQueue,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ReEmbedService' });
  }

  async reEmbedAll(sources: WatchSourceConfig[], options?: ReEmbedOptions): Promise<void> {
    this.logger.info(`Re-embedding all sources: count=${sources.length}`);

    for (const source of sources) {
      await this.reEmbedSourceInternal(source, options);
    }
  }

  async reEmbedSource(sourceId: string, sources: WatchSourceConfig[], options?: ReEmbedOptions): Promise<void> {
    this.logger.info(`Re-embedding source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    await this.reEmbedSourceInternal(source, options);
  }

  async reEmbedFile(
    filePath: string,
    sourceId: string,
    sources: WatchSourceConfig[],
    options?: ReEmbedOptions,
  ): Promise<void> {
    this.logger.info(`Re-embedding single file; path="${filePath}", source="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    // Look up the tracker for this file
    const trackers = await this.fileTrackerRepository.findTrackedBySourceId(source.id);
    const tracker = trackers.find(t => t.filePath === filePath);

    if (!tracker) {
      this.logger.info(`File not tracked yet, treating as new file: path="${filePath}"`);
      // Process the file directly using ProcessFileUseCase
      const result = await this.processFileUseCase.execute({
        filePath,
        eventType: 'add',
        sourceId: source.id,
        memoryBank: source.memoryBank,
        sourceConfig: source,
      });
      if (result.isKo()) {
        this.logger.error(`File processing failed: path="${filePath}", error="${result.getFormattedErrors()}"`);
      }
      return;
    }

    await this.reEmbedFileInternal(tracker, source, options);
  }

  private async reEmbedSourceInternal(source: WatchSourceConfig, options?: ReEmbedOptions): Promise<void> {
    const trackers = await this.fileTrackerRepository.findTrackedBySourceId(source.id);
    this.logger.info(`Tracked files found for re-embedding: source="${source.id}", count=${trackers.length}`);

    for (const tracker of trackers) {
      await this.reEmbedFileInternal(tracker, source, options);
    }
  }

  private async reEmbedFileInternal(
    tracker: FileTracker,
    source: WatchSourceConfig,
    options?: ReEmbedOptions,
  ): Promise<ReEmbedOutcome> {
    const filePath = tracker.filePath;

    // Read the stored chunk set from bensyne (read-only, zero LLM)
    const chunksResult = await this.bensyneClient.getFileChunks(filePath, source.memoryBank);
    if (chunksResult.isKo()) {
      this.logger.error(
        `Failed to read stored chunks: path="${filePath}", error="${chunksResult.getFormattedErrors()}"`,
      );
      return { status: 'error', reason: 'get-file-chunks-failed' };
    }
    const fileChunks = chunksResult.getValue();

    // FILE_NOT_FOUND → no embeddings to re-embed
    if (fileChunks.status === 'FILE_NOT_FOUND') {
      this.logger.debug(`File not found on bensyne side, skipping: path="${filePath}"`);
      return { status: 'skipped-healthy' };
    }

    // Check for chunks with missing embeddings (memory_status is null)
    const missingEmbeddings = fileChunks.chunks.filter(chunk => chunk.memoryStatus === null);

    if (missingEmbeddings.length === 0) {
      this.logger.debug(`All chunks already embedded, skipping: path="${filePath}"`);
      return { status: 'skipped-healthy' };
    }

    this.logger.info(
      `Re-embedding file with missing embeddings: path="${filePath}", chunks=${missingEmbeddings.length}/${fileChunks.chunks.length}`,
    );

    if (options?.dryRun === true) {
      this.logger.info(`DRY-RUN: would re-embed ${missingEmbeddings.length} chunk(s): path="${filePath}"`);
      return { status: 'dry-run', wouldReembed: missingEmbeddings.length };
    }

    // Compute file hash
    let fileHash: string | undefined;
    try {
      fileHash = await this.fileHasherService.compute(filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to compute file hash, continuing without it: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    // Get hardware ID
    let hardwareId: string | undefined;
    try {
      hardwareId = await this.hardwareIdDetectorService.getHardwareId();
    } catch (error) {
      this.logger.warn(
        `Failed to get hardware ID, continuing without it: error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    // Read file content directly
    let fileContent: string;
    try {
      const fs = await import('fs/promises');
      fileContent = await fs.readFile(filePath, 'utf-8');
    } catch (error) {
      this.logger.error(
        `Failed to read file content: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return { status: 'error', reason: 'read-failed' };
    }

    // Re-chunk WITH enrichment and force re-embed
    const chunksResult2 = await this.chunkContentUseCase.execute({
      content: fileContent,
      filePath,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
      fileHash,
      hardwareId,
    });

    if (chunksResult2.isKo()) {
      this.logger.error(
        `Failed to re-chunk file: path="${filePath}", error="${chunksResult2.getFormattedErrors()}"`,
      );
      return { status: 'error', reason: 're-chunk-failed' };
    }

    // Serialize the submit through the queue
    await this.processingQueue.addToQueue(async () => {
      const result = await this.ingestChunkUseCase.execute({
        chunks: chunksResult2.getValue(),
        sourceId: source.id,
        metadata: { filePath },
        fileHash,
        hardwareId,
        forceReembed: true,
      });
      if (result.isKo()) {
        this.logger.error(`Re-embed submit failed: path="${filePath}", error="${result.getFormattedErrors()}"`);
      }
    });

    this.logger.info(`Re-embed submitted: path="${filePath}", chunks=${chunksResult2.getValue().length}`);
    return { status: 're-embedded', chunks: chunksResult2.getValue().length };
  }
}