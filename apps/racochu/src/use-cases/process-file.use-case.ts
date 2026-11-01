import { Injectable } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import * as fs from 'fs/promises';
import { z } from 'zod';
import {
  DEFAULT_CONTENT_FILTER_OPTIONS,
  classifyContent,
} from '../application/services/content-classifier.service';
import {
  FILE_EVENTS,
  FILE_OPERATIONS,
  FileAddedEvent,
  FileChangedEvent,
  FileDeletedEvent,
} from '../domain/events/file-events';
import { FILE_TRACKER_SKIP_REASON, FileTrackerSkipReason } from '../domain/file-tracker.aggregate';
import { WatchSourceConfig, resolvedWatchSourceConfigSchema } from '../infrastructure/config/config-schemas';
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
  // R1: internal seam — validate the NORMALIZED shape (resolvedPaths
  // required, no operator key-XOR); the entry gate lives in config loading.
  sourceConfig: resolvedWatchSourceConfigSchema,
  // DEC-A3: deliberate corrective/override re-ingests (force-reprocess,
  // stale-tracker repair, recover FILE_NOT_FOUND) bypass the hash gate.
  // Absent means false — every ordinary ingest path is gated.
  forceIngest: z.boolean().optional(),
});

export type ProcessFileParams = z.infer<typeof processFileParamsSchema>;

/**
 * C8 classification marker (T6, additive): distinguishes the two skip
 * families on the ok-payload so batch loops can count them without extra
 * DB reads. Set ONLY at the existing skip return sites.
 */
export type ProcessFileSkipMarker = 'unchanged' | 'terminal';

/**
 * Additive outcome payload of ProcessFileUseCase.execute (spec C8, T6).
 * Strictly additive: `skipped` is set only at skip return sites; every
 * ordinary/early return keeps its previous behavior-less payload. Result
 * ok/ko semantics are unchanged by this type.
 */
export interface ProcessFileOutcome {
  skipped?: ProcessFileSkipMarker;
}

export interface IngestFileResult {
  memoryIds: string[];
  /** C8 additive marker — set only by the skip-return sites of ingestFile. */
  skipped?: ProcessFileSkipMarker;
}

/**
 * Internal CHANGE-path hand-off: the hash the gate in handleChange already
 * computed. Its structural presence means "this file was already hashed once"
 * — the value itself may be undefined when the compute itself failed.
 */
interface PrecomputedFileHash {
  fileHash?: string;
}

/** Inputs of the hash gate, as read via FileMemoryTrackerService. */
interface IngestGateState {
  storedHash: string | null;
  skipReason: string | null;
  tracked: boolean;
}

const defaultSourceConfig = (): WatchSourceConfig => ({
  id: 'default',
  path: '',
  resolvedPaths: [''],
  sourceType: SOURCE_TYPES.VAULT,
  memoryBank: 'default',
  description: '',
  exclude: [],
  debounceMs: 3000,
  contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
  autoPopulate: true,
});

@Injectable()
export class ProcessFileUseCase extends BaseUseCase<ProcessFileParams, ProcessFileOutcome> {
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

  protected async executeInternal(params: ProcessFileParams): Promise<Result<ProcessFileOutcome>> {
    this.logger.debug(
      `Processing file: path="${params.filePath}", event="${params.eventType}", source="${params.sourceId}"`,
    );

    // Skip if already processing this file — chokidar may fire multiple events
    if (this.processing.has(params.filePath)) {
      this.logger.debug(`Skipping duplicate event: path="${params.filePath}", event="${params.eventType}"`);
      return Result.ok(undefined as unknown as ProcessFileOutcome);
    }

    this.processing.add(params.filePath);

    // C8 (T6): the handler's outcome marker (skip classification) is captured
    // here so execute() carries it on its ok-payload. Strictly additive —
    // ko handling and all ok-semantics are unchanged.
    let handlerOutcome: ProcessFileOutcome | undefined;

    // Queue the processing
    await this.processingQueue.addToQueue(async () => {
      try {
        let result: Result<ProcessFileOutcome>;

        const handlers: Record<string, (params: ProcessFileParams) => Promise<Result<ProcessFileOutcome>>> = {
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

        if (result.isOk()) {
          handlerOutcome = result.getValue();
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

    // Same value-less ok semantics as before (ko outcomes were and remain
    // log-only here); the payload only ever carries the C8 skip marker.
    return Result.ok(handlerOutcome as unknown as ProcessFileOutcome);
  }

  private async handleAdd(params: ProcessFileParams): Promise<Result<ProcessFileOutcome>> {
    const result = await this.ingestFile(params);
    if (result.isKo()) {
      return result as unknown as Result<ProcessFileOutcome>;
    }
    // C8 (T6) propagation ONLY — an ingest with a skip classification carries
    // its marker up; an ordinary ingest stays marker-free.
    const { skipped } = result.getValue();
    if (skipped) {
      return Result.ok({ skipped });
    }
    return Result.ok(undefined as unknown as ProcessFileOutcome);
  }

  private async handleChange(params: ProcessFileParams): Promise<Result<ProcessFileOutcome>> {
    // Hash gate (spec C3.2 / DEC-A1): the unchanged-file check MUST run BEFORE
    // Step 1/Step 2 — a post-forget skip would tombstone live memories with
    // no re-ingest (silent data loss; the DEC-0036 ordering below is
    // load-bearing). Inputs: compute the hash first, read the gate state
    // second; either failure degrades to "not gated" (fail-open, spec §5) —
    // a dead DB never suppresses ingestion, and the computed hash is passed
    // into ingestFile (spec §7: one SHA-256 per file, never two).
    const fileHash = await this.computeFileHashBestEffort(params.filePath);
    const gateState = await this.readIngestGateStateBestEffort(params.filePath);

    if (this.shouldSkipUnchanged(params, gateState, fileHash)) {
      this.logHashGateSkip(params.filePath, fileHash as string);
      // C8 (T6): gate-skip classification rides the ok-payload.
      return Result.ok({ skipped: 'unchanged' });
    }

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
        const forgetResult = await this.bensyneClient.forgetByFile(params.filePath, params.memoryBank);
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

    // Step 3: Ingest new content — re-creates the file row and new chunks.
    // The hash already computed for the gate is passed down: the file is
    // hashed exactly once even though the gate ran first.
    const ingestResult = await this.ingestFile(params, { fileHash });
    if (ingestResult.isKo()) {
      return ingestResult as unknown as Result<ProcessFileOutcome>;
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

    // C8 (T6) propagation ONLY: a terminal skip reached through the change
    // flow (content rewritten to a never-ingestable class) carries its
    // marker; the old-memory cleanup above ran exactly as before.
    const { skipped } = ingestResult.getValue();
    if (skipped) {
      return Result.ok({ skipped });
    }
    return Result.ok(undefined as unknown as ProcessFileOutcome);
  }

  private async ingestFile(
    params: ProcessFileParams,
    precomputedHash?: PrecomputedFileHash,
  ): Promise<Result<IngestFileResult>> {
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
        return Result.ok({ memoryIds: [] }); // Skip gracefully — NO skip marker:
        // not-found is neither gated nor terminal; C8 counts only those two.
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

    // Compute file hash FIRST (spec C3.3 — moved to immediately after the
    // content read; non-fatal), over raw file bytes, consistent on both the
    // write and read sides. On the CHANGE path the gate in handleChange
    // already computed it and hands it in: one SHA-256 per file, never two
    // (spec §7).
    let fileHash: string | undefined;
    if (precomputedHash) {
      fileHash = precomputedHash.fileHash;
    } else {
      fileHash = await this.computeFileHashBestEffort(params.filePath);
    }

    // Add-path hash gate (spec C3.3): same DEC-0084 comparison rule as the
    // CHANGE path — only a non-null stored hash equal to a computed hash
    // skips; forceIngest overrides. A CHANGE call (precomputedHash present)
    // already passed this gate in handleChange and is never re-gated.
    if (!precomputedHash) {
      const gateState = await this.readIngestGateStateBestEffort(params.filePath);
      if (this.shouldSkipUnchanged(params, gateState, fileHash)) {
        this.logHashGateSkip(params.filePath, fileHash as string);
        // C8 (T6): gate-skip classification rides the ok-payload.
        return Result.ok({ memoryIds: [], skipped: 'unchanged' });
      }
    }

    // Get hardware ID (non-fatal). Moved with the hash: the terminal-skip
    // records below persist it alongside the content hash (spec C2).
    let hardwareId: string | undefined;
    try {
      hardwareId = await this.hardwareIdDetectorService.getHardwareId();
    } catch (error) {
      this.logger.warn(
        `Failed to get hardware ID, continuing without it: error="${error instanceof Error ? error.message : String(error)}"`,
      );
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
      // Quarantine the exact bytes (spec C3.4): without a recorded skip row
      // this same verdict would repeat on every future pass (M2 class).
      await this.recordTerminalSkipBestEffort(
        params,
        fileHash,
        hardwareId,
        FILE_TRACKER_SKIP_REASON.CONTENT_FILTERED,
      );
      // C8 (T6): terminal-skip classification rides the ok-payload.
      return Result.ok({ memoryIds: [], skipped: 'terminal' });
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

    // Never-ingestable class (spec C3.4): zero-byte / whitespace-only content.
    // Pre-empts ChunkContentUseCase's content.min(1) zod rejection (findings
    // §3, ×179 too_small) — that contract stays intact for programmatic
    // callers (DEC-A2); the use case records the terminal skip instead.
    if (content.trim().length === 0) {
      this.logger.info(`Skipping empty content: path="${params.filePath}"`);
      await this.recordTerminalSkipBestEffort(
        params,
        fileHash,
        hardwareId,
        FILE_TRACKER_SKIP_REASON.EMPTY_CONTENT,
      );
      // C8 (T6): terminal-skip classification rides the ok-payload.
      return Result.ok({ memoryIds: [], skipped: 'terminal' });
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
      // Terminal skip for zero-chunk producers (spec C3.4) — same quarantine;
      // the existing ok-level outcome is unchanged.
      await this.recordTerminalSkipBestEffort(
        params,
        fileHash,
        hardwareId,
        FILE_TRACKER_SKIP_REASON.ZERO_CHUNKS,
      );
      // C8 (T6): terminal-skip classification rides the ok-payload.
      return Result.ok({ memoryIds: [], skipped: 'terminal' });
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

  /**
   * Compute the file hash best-effort: on failure log warn and continue
   * without a hash (spec §5 fail-open — a broken hash source must never
   * block ingestion; the gate simply cannot fire without a computed hash).
   */
  private async computeFileHashBestEffort(filePath: string): Promise<string | undefined> {
    try {
      return await this.fileHasherService.compute(filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to compute file hash, continuing without it: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return undefined;
    }
  }

  /**
   * Read the ingest-gate state best-effort. The service THROWS on a DB read
   * failure by design (T2); the gate owns the fail-open decision — a dead DB
   * may degrade racochu to today's ungated behavior, never suppress files.
   */
  private async readIngestGateStateBestEffort(filePath: string): Promise<IngestGateState | undefined> {
    try {
      return await this.fileMemoryTrackerService.getIngestGateState(filePath);
    } catch (error) {
      this.logger.warn(
        `Ingest gate state read failed, proceeding without gating: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return undefined;
    }
  }

  /**
   * Gate comparison rule, copied from RecoverService step 5 (DEC-0084):
   * fires ONLY when a stored hash exists AND the current hash is computable
   * AND the two are equal. Every other combination proceeds exactly as
   * today. forceIngest (DEC-A3) marks deliberate corrective re-ingests and
   * always bypasses.
   */
  private shouldSkipUnchanged(
    params: ProcessFileParams,
    gateState: IngestGateState | undefined,
    fileHash: string | undefined,
  ): boolean {
    if (params.forceIngest === true) {
      return false;
    }
    if (fileHash === undefined || gateState === undefined) {
      return false;
    }
    if (gateState.storedHash === null) {
      return false;
    }
    return gateState.storedHash === fileHash;
  }

  /** Operator-facing skip line — the exact contract string (spec C8). */
  private logHashGateSkip(filePath: string, fileHash: string): void {
    this.logger.info(
      `Skipping unchanged file (hash gate): path="${filePath}", fileHash="${fileHash.substring(0, 12)}"`,
    );
  }

  /**
   * Record a terminal-skip decision for never-ingestable content (C2 service,
   * throws on write failure). Recording is NON-FATAL by design (spec §5): a
   * failed write only degrades the file back to today's retried-every-pass
   * behavior, never a processing failure. Requires the content hash — without
   * it the row would carry no decision to re-match, so the write is skipped.
   */
  private async recordTerminalSkipBestEffort(
    params: ProcessFileParams,
    fileHash: string | undefined,
    hardwareId: string | undefined,
    skipReason: FileTrackerSkipReason,
  ): Promise<void> {
    if (fileHash === undefined) {
      this.logger.warn(
        `Terminal skip not recorded, no file hash available for these bytes: path="${params.filePath}", reason="${skipReason}"`,
      );
      return;
    }
    try {
      await this.fileMemoryTrackerService.recordTerminalSkip(
        params.filePath,
        params.sourceId,
        params.memoryBank,
        fileHash,
        hardwareId ?? null,
        skipReason,
      );
      // Searchable observability token (spec C8): one per reason value.
      this.logger.info(`terminal-skip-recorded reason=${skipReason} path="${params.filePath}"`);
    } catch (error) {
      this.logger.warn(
        `Failed to record terminal skip, continuing (file re-attempts next pass): path="${params.filePath}", reason="${skipReason}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }
  }

  private async handleDelete(params: ProcessFileParams): Promise<Result<ProcessFileOutcome>> {
    this.logger.info(`File deleted; path="${params.filePath}", source="${params.sourceId}"`);

    const memoryIds = await this.fileMemoryTrackerService.getMemoryIds(params.filePath);

    if (memoryIds.length === 0) {
      this.logger.debug(`No memory mappings found for deletion; path="${params.filePath}"`);
      return Result.ok(undefined as unknown as ProcessFileOutcome);
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

    return Result.ok(undefined as unknown as ProcessFileOutcome);
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
