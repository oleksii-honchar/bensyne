import { Injectable } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import * as fs from 'fs/promises';
import { z } from 'zod';
import { DEFAULT_CONTENT_FILTER_OPTIONS, classifyContent } from '../application/content-classifier.service';
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
import { guardBase64Content } from '../utils/base64-guard';
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

export interface IngestFileResult {
  memoryIds: string[];
}

const defaultSourceConfig = (): WatchSourceConfig => ({
  id: 'default',
  path: '',
  sourceType: SOURCE_TYPES.VAULT,
  memoryBank: 'default',
  description: '',
  exclude: [],
  debounceMs: 3000,
  contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
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

  private async handleAdd(params: ProcessFileParams): Promise<Result<void>> {
    const result = await this.ingestFile(params);
    if (result.isKo()) {
      return result as unknown as Result<void>;
    }
    return Result.ok(undefined as unknown as void);
  }

  private async handleChange(params: ProcessFileParams): Promise<Result<void>> {
    // Step 1: Get old memory IDs (for later tracker cleanup)
    const oldMemoryIds = await this.fileMemoryTrackerService.getMemoryIds(params.filePath);

    // Step 2: Forget the file's OLD non-shared memories BEFORE re-ingestion.
    // forgetByFile (MCP forgetFile) bypasses the forgetMemory guard which is
    // restricted to pure_memories banks (file-backed banks like agent-sessions
    // return MEMORY_BANK_NOT_SUPPORTED). It also preserves shared memories.
    // CRITICAL ordering: forgetFile tombstones the file and would destroy the
    // newly-ingested memories if called after ingest — so it runs FIRST.
    // Failure is non-fatal: ingest proceeds and tracker cleanup still runs.
    if (oldMemoryIds.length > 0) {
      try {
        const forgetResult = await this.bensyneClient.forgetByFile(
          params.filePath,
          params.memoryBank,
        );
        if (forgetResult.isKo()) {
          this.logger.warn(
            `forgetByFile failed on change, continuing with ingest: path="${params.filePath}", memoryBank="${params.memoryBank}", error="${forgetResult.getFormattedErrors()}"`,
          );
        }
      } catch (error) {
        this.logger.warn(
          `forgetByFile threw on change, continuing with ingest: path="${params.filePath}", memoryBank="${params.memoryBank}", error="${error instanceof Error ? error.message : String(error)}"`,
        );
      }
    }

    // Step 3: Ingest new content — re-creates the file row and new chunks
    const ingestResult = await this.ingestFile(params);
    if (ingestResult.isKo()) {
      return ingestResult as unknown as Result<void>;
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

    return Result.ok(undefined as unknown as void);
  }

  private async ingestFile(params: ProcessFileParams): Promise<Result<IngestFileResult>> {
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
        return Result.ok({ memoryIds: [] }); // Skip gracefully
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

    // Content filter — machine-generated dumps (git merge-tree output, diff
    // dumps, etc.) must never be chunked or enriched. This is the ingest gate
    // covering --watch, --process-only, and --resume (all route here).
    // `enabled: false` short-circuits inside the classifier → not filtered.
    const classification = classifyContent(content, params.sourceConfig.contentFilter);
    if (classification.filtered) {
      this.logger.info(
        `Skipping filtered file: path="${params.filePath}", reasons="${classification.reasons.join('; ')}"`,
      );
      return Result.ok({ memoryIds: [] });
    }

    // Guard against whole-file base64 blobs (ReDoS prevention): mnemosyne's
    // fact extractor catastrophically backtracks on long whitespace-free
    // base64 runs, so replace detected blobs with a placeholder before
    // chunking. The placeholder is what flows downstream (into mnemosyne).
    const guarded = guardBase64Content(content);
    if (guarded.sanitized) {
      this.logger.warn(
        `Whole-file base64 blob detected, replaced with placeholder: path="${params.filePath}", bytes="${content.length}"`,
      );
      content = guarded.content;
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
      return chunksResult as unknown as Result<IngestFileResult>;
    }

    const chunks = chunksResult.getValue();
    if (chunks.length === 0) {
      this.logger.debug(`No chunks generated; path="${params.filePath}"`);
      return Result.ok({ memoryIds: [] });
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
      return ingestResult as unknown as Result<IngestFileResult>;
    }

    const { memoryIds } = ingestResult.getValue();

    this.logger.info(
      `File processed: path="${params.filePath}", event="${params.eventType}", chunks=${chunks.length}, memoryIds=${memoryIds.length}`,
    );

    return Result.ok({ memoryIds });
  }

  private async handleDelete(params: ProcessFileParams): Promise<Result<void>> {
    this.logger.info(`File deleted; path="${params.filePath}", source="${params.sourceId}"`);

    const memoryIds = await this.fileMemoryTrackerService.getMemoryIds(params.filePath);

    if (memoryIds.length === 0) {
      this.logger.debug(`No memory mappings found for deletion; path="${params.filePath}"`);
      return Result.ok(undefined as unknown as void);
    }

    this.logger.debug(`Forgetting file for deleted file; path="${params.filePath}"`);

    // Use file-level forget (forgetFile tool) instead of per-memory loop.
    // The forgetFile tool bypasses the recall-only gate and handles the
    // shared-memory guard on the bensyne side. Failure is non-blocking:
    // a single-file delete failure must not block the queue.
    const forgetResult = await this.bensyneClient.forgetByFile(params.filePath, params.memoryBank);
    if (forgetResult.isKo()) {
      this.logger.warn(
        `forgetByFile failed, continuing with tracker cleanup: path="${params.filePath}", memoryBank="${params.memoryBank}", error="${forgetResult.getFormattedErrors()}"`,
      );
    }

    // Tracker cleanup — always performed, non-fatal.
    try {
      await this.fileMemoryTrackerService.deleteByFilePath(params.filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to deleteByFilePath for deleted file; path="${params.filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    this.logger.info(`Delete completed; path="${params.filePath}"`);

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
