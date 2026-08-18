import { Injectable } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import * as fs from 'fs/promises';
import { z } from 'zod';
import {
  FILE_EVENTS,
  FILE_OPERATIONS,
  FileAddedEvent,
  FileChangedEvent,
  FileDeletedEvent,
} from '../domain/events/file-events';
import { WatchSourceConfig, watchSourceConfigSchema } from '../infrastructure/config/config-schemas';
import { SOURCE_TYPES } from '../infrastructure/config/source-types';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileHasherService } from '../infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { HardwareIdDetectorService } from '../infrastructure/services/hardware-id-detector.service';
import { BaseUseCase } from '../utils/base-use-case';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';
import { ChunkContentUseCase } from './chunk-content.use-case';
import { IngestChunkUseCase } from './ingest-chunk.use-case';

const processFileParamsSchema = z.object({
  filePath: z.string().min(1),
  eventType: z.enum([FILE_OPERATIONS.ADD, FILE_OPERATIONS.CHANGE, FILE_OPERATIONS.DELETE]),
  sourceId: z.string().min(1),
  memoryBank: z.string().min(1),
  sourceConfig: watchSourceConfigSchema,
});

export type ProcessFileParams = z.infer<typeof processFileParamsSchema>;

const defaultSourceConfig = (): WatchSourceConfig => ({
  id: 'default',
  path: '',
  sourceType: SOURCE_TYPES.VAULT,
  memoryBank: 'default',
  description: '',
  exclude: [],
  debounceMs: 3000,
});

@Injectable()
export class ProcessFileUseCase extends BaseUseCase<ProcessFileParams, void> {
  /**
   * Tracks files currently being processed (queued or in-progress).
   * Prevents duplicate processing when chokidar fires multiple events for
   * the same file change — the second event is skipped.
   */
  private readonly processing = new Set<string>();

  constructor(
    private readonly chunkContentUseCase: ChunkContentUseCase,
    private readonly ingestChunkUseCase: IngestChunkUseCase,
    private readonly processingQueue: FileProcessingQueue,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    private readonly fileHasherService: FileHasherService,
    private readonly hardwareIdDetectorService: HardwareIdDetectorService,
    logger: BasePinoLogger,
  ) {
    super(logger);
    this.logger = this.logger.child({ component: 'ProcessFileUseCase' });
  }

  protected validateParams(params: ProcessFileParams): Result<ProcessFileParams> {
    const parsed = processFileParamsSchema.safeParse(params);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails(
          'Invalid process file params: ' + parsed.error.message,
          'InvalidProcessFileParams',
        ),
      ]);
    }
    return Result.ok(parsed.data);
  }

  protected async executeInternal(params: ProcessFileParams): Promise<Result<void>> {
    this.logger.debug(
      `Processing file: path="${params.filePath}", event="${params.eventType}", source="${params.sourceId}"`,
    );

    // Skip if already processing this file — chokidar may fire multiple events
    if (this.processing.has(params.filePath)) {
      this.logger.debug(`Skipping duplicate event: path="${params.filePath}", event="${params.eventType}"`);
      return Result.ok(undefined as unknown as void);
    }

    this.processing.add(params.filePath);

    // Queue the processing
    await this.processingQueue.addToQueue(async () => {
      try {
        let result: Result<void>;

        const handlers: Record<string, (params: ProcessFileParams) => Promise<Result<void>>> = {
          add: this.handleAdd.bind(this),
          change: this.handleChange.bind(this),
          delete: this.handleDelete.bind(this),
        };
        const handler = handlers[params.eventType];
        if (!handler) {
          result = Result.ko([
            new ErrorWithDetails(`Unknown event type: ${params.eventType}`, 'UnknownEventType'),
          ]);
        } else {
          result = await handler(params);
        }

        if (result.isKo()) {
          this.logger.error(
            `File processing failed: path="${params.filePath}", event="${params.eventType}", error="${result.getFormattedErrors()}"`,
          );
        }
      } finally {
        this.processing.delete(params.filePath);
      }
    });

    return Result.ok(undefined as unknown as void);
  }

  private async forgetOldMemoriesByIds(
    memoryIds: string[],
    params: ProcessFileParams,
  ): Promise<Result<void>> {
    if (memoryIds.length === 0) {
      this.logger.debug(`No old memories to forget; path="${params.filePath}"`);
      return Result.ok(undefined as unknown as void);
    }

    this.logger.info(
      `Forgetting ${memoryIds.length} old memories after re-ingestion; path="${params.filePath}"`,
    );

    let failedCount = 0;
    const errors: ErrorWithDetails[] = [];

    for (const memoryId of memoryIds) {
      try {
        const result = await this.bensyneClient.forget(memoryId, params.memoryBank);
        if (result.isKo()) {
          failedCount++;
          errors.push(
            new ErrorWithDetails(
              `Failed to forget memory ${memoryId}: ${result.getFormattedErrors()}`,
              'ForgetMemoryError',
            ),
          );
          this.logger.warn(
            `Failed to forget memory; memoryId="${memoryId}", error="${result.getFormattedErrors()}"`,
          );
        }
      } catch (error) {
        failedCount++;
        errors.push(
          new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'ForgetMemoryError'),
        );
        this.logger.warn(
          `Error forgetting memory; memoryId="${memoryId}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }

    this.logger.info(
      `Old memories forgotten: path="${params.filePath}", total="${memoryIds.length}", forgotten="${memoryIds.length - failedCount}", failed="${failedCount}"`,
    );

    if (failedCount > 0) {
      return Result.ko(errors);
    }

    return Result.ok(undefined as unknown as void);
  }

  private async handleAdd(params: ProcessFileParams): Promise<Result<void>> {
    return this.ingestFile(params);
  }

  private async handleChange(params: ProcessFileParams): Promise<Result<void>> {
    // Step 1: Get old memory IDs (for later forget)
    const oldMemoryIds = await this.fileMemoryTrackerService.getMemoryIds(params.filePath);

    // Step 2: Ingest new content — new memory IDs tracked alongside old ones
    const ingestResult = await this.ingestFile(params);
    if (ingestResult.isKo()) {
      return ingestResult;
    }

    // Step 3: Forget old memories from Mnemosyne (continue on failure)
    if (oldMemoryIds.length > 0) {
      const forgetResult = await this.forgetOldMemoriesByIds(oldMemoryIds, params);
      if (forgetResult.isKo()) {
        this.logger.warn(
          `Old memory cleanup failed, new content ingested successfully: path="${params.filePath}", error="${forgetResult.getFormattedErrors()}"`,
        );
      }
    }

    // Step 4: Remove old memory IDs from tracker (non-fatal)
    if (oldMemoryIds.length > 0) {
      try {
        await this.fileMemoryTrackerService.forgetMemories(params.filePath, oldMemoryIds);
      } catch (error) {
        this.logger.warn(
          `Failed to remove old memories from tracker; path="${params.filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }

    return ingestResult;
  }

  private async ingestFile(params: ProcessFileParams): Promise<Result<void>> {
    // Check file existence before processing
    let fileExists: boolean;
    try {
      await fs.access(params.filePath, fs.constants.F_OK);
      fileExists = true;
    } catch {
      fileExists = false;
    }

    if (!fileExists) {
      this.logger.warn(`File not found, retrying in 100ms: path="${params.filePath}"`);
      await new Promise(resolve => setTimeout(resolve, 100));
      try {
        await fs.access(params.filePath, fs.constants.F_OK);
        fileExists = true;
      } catch {
        this.logger.warn(`File still not found after retry, skipping: path="${params.filePath}"`);
        return Result.ok(undefined as unknown as void); // Skip gracefully
      }
    }

    // Read file content
    let content: string;
    try {
      content = await fs.readFile(params.filePath, 'utf-8');
    } catch (error) {
      return Result.ko([
        new ErrorWithDetails(error instanceof Error ? error.message : String(error), 'FileReadError', {
          filePath: params.filePath,
        }),
      ]);
    }

    // Compute file hash (non-fatal)
    let fileHash: string | undefined;
    try {
      fileHash = await this.fileHasherService.compute(params.filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to compute file hash, continuing without it: path="${params.filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    // Get hardware ID (non-fatal)
    let hardwareId: string | undefined;
    try {
      hardwareId = await this.hardwareIdDetectorService.getHardwareId();
    } catch (error) {
      this.logger.warn(
        `Failed to get hardware ID, continuing without it: error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    // Chunk content
    const chunksResult = await this.chunkContentUseCase.execute({
      content,
      filePath: params.filePath,
      sourceId: params.sourceId,
      memoryBank: params.memoryBank,
      sourceConfig: params.sourceConfig,
      fileHash,
      hardwareId,
    });

    if (chunksResult.isKo()) {
      return chunksResult as unknown as Result<void>;
    }

    const chunks = chunksResult.getValue();
    if (chunks.length === 0) {
      this.logger.debug(`No chunks generated; path="${params.filePath}"`);
      return Result.ok(undefined as unknown as void);
    }

    this.logger.info(`Chunks created; path="${params.filePath}", chunks=${chunks.length}`);

    // Ingest chunks
    const ingestResult = await this.ingestChunkUseCase.execute({
      chunks,
      sourceId: params.sourceId,
      metadata: {
        filePath: params.filePath,
        eventType: params.eventType,
      },
      fileHash,
      hardwareId,
    });

    if (ingestResult.isKo()) {
      return ingestResult as unknown as Result<void>;
    }

    this.logger.info(
      `File processed: path="${params.filePath}", event="${params.eventType}", chunks=${chunks.length}`,
    );

    return Result.ok(undefined as unknown as void);
  }

  private async handleDelete(params: ProcessFileParams): Promise<Result<void>> {
    this.logger.info(`File deleted; path="${params.filePath}", source="${params.sourceId}"`);

    const memoryIds = await this.fileMemoryTrackerService.getMemoryIds(params.filePath);

    if (memoryIds.length === 0) {
      this.logger.debug(`No memory mappings found for deletion; path="${params.filePath}"`);
      return Result.ok(undefined as unknown as void);
    }

    this.logger.debug(`Forgetting ${memoryIds.length} memories for deleted file; path="${params.filePath}"`);

    let failedCount = 0;
    for (const memoryId of memoryIds) {
      try {
        const result = await this.bensyneClient.forget(memoryId, params.memoryBank);
        if (result.isKo()) {
          failedCount++;
          this.logger.warn(
            `Failed to forget memory; memoryId="${memoryId}", memoryBank="${params.memoryBank}", error="${result.getFormattedErrors()}"`,
          );
        }
      } catch (error) {
        failedCount++;
        this.logger.warn(
          `Error forgetting memory; memoryId="${memoryId}", memoryBank="${params.memoryBank}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }

    try {
      await this.fileMemoryTrackerService.deleteByFilePath(params.filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to deleteByFilePath for deleted file; path="${params.filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    this.logger.info(
      `Delete completed; path="${params.filePath}", memoriesForgotten="${memoryIds.length - failedCount}", failures="${failedCount}"`,
    );

    return Result.ok(undefined as unknown as void);
  }

  @OnEvent(FILE_EVENTS.ADDED)
  async handleFileAdded(event: FileAddedEvent): Promise<void> {
    await this.execute({
      filePath: event.path,
      eventType: FILE_OPERATIONS.ADD,
      sourceId: 'default',
      memoryBank: 'default',
      sourceConfig: defaultSourceConfig(),
    });
  }

  @OnEvent(FILE_EVENTS.CHANGED)
  async handleFileChanged(event: FileChangedEvent): Promise<void> {
    await this.execute({
      filePath: event.path,
      eventType: 'change',
      sourceId: 'default',
      memoryBank: 'default',
      sourceConfig: defaultSourceConfig(),
    });
  }

  @OnEvent(FILE_EVENTS.DELETED)
  async handleFileDeleted(event: FileDeletedEvent): Promise<void> {
    await this.execute({
      filePath: event.path,
      eventType: 'delete',
      sourceId: 'default',
      memoryBank: 'default',
      sourceConfig: defaultSourceConfig(),
    });
  }
}
