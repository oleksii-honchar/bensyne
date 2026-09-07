import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import { FileTracker } from '../domain/file-tracker.aggregate';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { FileTrackerRepository } from '../infrastructure/repositories/file-tracker.repository';
import { BensyneClient, StoredChunkInfo } from '../infrastructure/services/bensyne-client.service';
import { FileHasherService } from '../infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { HardwareIdDetectorService } from '../infrastructure/services/hardware-id-detector.service';
import { ChunkContentUseCase } from '../use-cases/chunk-content.use-case';
import { IngestChunkUseCase } from '../use-cases/ingest-chunk.use-case';
import { ProcessFileUseCase } from '../use-cases/process-file.use-case';
import { classifyContent } from './content-classifier.service';

/**
 * Outcome of the per-file recovery decision table (spec §4.2).
 * `error` carries a human-readable reason for the failure paths.
 */
export type RecoverOutcome =
  | { status: 'skipped-missing-on-disk' }
  | { status: 'skipped-filtered' }
  | { status: 'reingested'; eventType: 'add' | 'change' }
  | { status: 'healthy' }
  | { status: 'repaired'; repairedChunks: number }
  | { status: 'dry-run'; wouldRepair: number }
  | { status: 'error'; reason: string };

/**
 * Optional recover-mode switches. `dryRun` runs the same verification but
 * skips the final submit step (spec §4.2 dry-run).
 */
export interface RecoverOptions {
  dryRun?: boolean;
}

/**
 * Recovers chunk-level gaps for files already tracked in the local database.
 *
 * Mirrors `ForceReprocessService` structure (injectable, child logger, per-file
 * loop) but iterates the DB (`FileTrackerRepository.findTrackedBySourceId`)
 * instead of the filesystem — untracked files are never touched.
 *
 * Decision table (spec §4.2):
 * 1. Tracker row exists, file missing on disk → skip + warn (non-destructive).
 * 2. `getFileChunks` → `FILE_NOT_FOUND` → full re-ingest via ProcessFileUseCase (add).
 * 3. current fileHash ≠ FileTracker.fileHash (non-null) → full re-ingest (change).
 * 4. FileTracker.fileHash null (legacy) → skip the hash gate; compare chunk sets.
 * 5. Chunk sets match, all `memoryStatus: "present"` → healthy — skip.
 * 6. Missing `chunk_index`(es) OR `memoryStatus: "missing"` → re-chunk WITH
 *    enrichment (config as-is), submit only the repair set via
 *    IngestChunkUseCase with `forceReembed: true`, then trackMemory (handled
 *    inside IngestChunkUseCase via metadata.filePath, mirroring ProcessFileUseCase).
 *
 * SERIALIZATION (critical): direct IngestChunkUseCase submits MUST be wrapped in
 * `processingQueue.addToQueue(...)` so the `waitForEmpty → exit` contract holds.
 * `addToQueue` is never called from inside a running queued task (the queue
 * deadlocks by design). `ProcessFileUseCase.execute` already enqueues itself.
 */
@Injectable()
export class RecoverService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly fileTrackerRepository: FileTrackerRepository,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly chunkContentUseCase: ChunkContentUseCase,
    private readonly ingestChunkUseCase: IngestChunkUseCase,
    private readonly bensyneClient: BensyneClient,
    private readonly fileHasherService: FileHasherService,
    private readonly hardwareIdDetectorService: HardwareIdDetectorService,
    private readonly processingQueue: FileProcessingQueue,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'RecoverService' });
  }

  async recoverAll(sources: WatchSourceConfig[], options?: RecoverOptions): Promise<void> {
    this.logger.info(`Recovering all sources: count=${sources.length}`);

    for (const source of sources) {
      await this.recoverSourceInternal(source, options);
    }
  }

  async recoverSource(
    sourceId: string,
    sources: WatchSourceConfig[],
    options?: RecoverOptions,
  ): Promise<void> {
    this.logger.info(`Recovering source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return;
    }

    await this.recoverSourceInternal(source, options);
  }

  private async recoverSourceInternal(source: WatchSourceConfig, options?: RecoverOptions): Promise<void> {
    const trackers = await this.fileTrackerRepository.findTrackedBySourceId(source.id);
    this.logger.info(`Tracked files found for recovery: source="${source.id}", count=${trackers.length}`);

    for (const tracker of trackers) {
      await this.recoverFile(tracker, source, options);
    }
  }

  /**
   * Per-file decision table (spec §4.2). Returns the outcome so callers can log
   * and future callers can aggregate. Never throws for per-file failures — each
   * row degrades to an outcome and the loop continues.
   */
  private async recoverFile(
    tracker: FileTracker,
    source: WatchSourceConfig,
    options?: RecoverOptions,
  ): Promise<RecoverOutcome> {
    const filePath = tracker.filePath;

    // 1. Non-destructive disk check — a tracker row without a file is skipped.
    try {
      await fs.access(filePath, fs.constants.F_OK);
    } catch {
      this.logger.warn(`Skipping tracked file for recovery; missing on disk: path="${filePath}"`);
      return { status: 'skipped-missing-on-disk' };
    }

    // 2. Read content + compute the local change-gate signals (non-fatal).
    let content: string;
    try {
      content = await fs.readFile(filePath, 'utf-8');
    } catch (error) {
      this.logger.warn(
        `Skipping tracked file for recovery; failed to read: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return { status: 'error', reason: 'read-failed' };
    }

    // 2a. Content filter — a filtered file must never be resurrected by
    // recover (no FILE_NOT_FOUND re-ingest, no repair). Runs before the
    // decision table. `enabled: false` short-circuits inside the classifier.
    const classification = classifyContent(content, source.contentFilter);
    if (classification.filtered) {
      this.logger.info(
        `Skipping filtered file for recovery: path="${filePath}", reasons="${classification.reasons.join('; ')}"`,
      );
      return { status: 'skipped-filtered' };
    }

    let fileHash: string | undefined;
    try {
      fileHash = await this.fileHasherService.compute(filePath);
    } catch (error) {
      this.logger.warn(
        `Failed to compute file hash, continuing without it: path="${filePath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    let hardwareId: string | undefined;
    try {
      hardwareId = await this.hardwareIdDetectorService.getHardwareId();
    } catch (error) {
      this.logger.warn(
        `Failed to get hardware ID, continuing without it: error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    // 3. Read the stored chunk set from bensyne (read-only, zero LLM).
    const chunksResult = await this.bensyneClient.getFileChunks(filePath, source.memoryBank);
    if (chunksResult.isKo()) {
      this.logger.error(
        `Failed to read stored chunks: path="${filePath}", error="${chunksResult.getFormattedErrors()}"`,
      );
      return { status: 'error', reason: 'get-file-chunks-failed' };
    }
    const fileChunks = chunksResult.getValue();

    // 4. FILE_NOT_FOUND → full re-ingest (add) — the file was never ingested.
    if (fileChunks.status === 'FILE_NOT_FOUND') {
      this.logger.info(`File absent on bensyne side, full re-ingest: path="${filePath}", event="add"`);
      await this.runProcessFile(tracker, source, 'add');
      return { status: 'reingested', eventType: 'add' };
    }

    // 5. Hash gate — a changed file goes through change semantics (forget stale
    //    + ingest). Legacy null tracker fileHash skips the gate.
    if (tracker.fileHash !== null && fileHash !== undefined && tracker.fileHash !== fileHash) {
      this.logger.info(`File changed since ingest, full re-ingest: path="${filePath}", event="change"`);
      await this.runProcessFile(tracker, source, 'change');
      return { status: 'reingested', eventType: 'change' };
    }

    // 6. Compute the expected chunk set locally, WITHOUT enrichment (CPU-only,
    //    zero LLM regardless of config — spec §4.3).
    const expectedResult = await this.chunkContentUseCase.execute({
      content,
      filePath,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
      fileHash,
      hardwareId,
      skipEnrichment: true,
    });
    if (expectedResult.isKo()) {
      this.logger.error(
        `Failed to compute expected chunk set: path="${filePath}", error="${expectedResult.getFormattedErrors()}"`,
      );
      return { status: 'error', reason: 'expected-chunk-set-failed' };
    }

    const expectedChunks = expectedResult.getValue();

    // 7. Compare expected vs stored — repair set = missing chunk_index(es) OR
    //    stored `memoryStatus: "missing"` (ADR-7 embedding-existence check).
    const storedByIndex = new Map<number, StoredChunkInfo>(
      fileChunks.chunks.map(chunk => [chunk.chunkIndex, chunk]),
    );
    // Always re-ingest files on recover — the hash dedup prevents duplicate
    // embeddings, and the ADR-11 content sync fix in bensyne-mcp updates stale
    // or empty memory text. This handles the edge case where FileChunk content
    // is correct but the memory's text field is empty (the original bug).
    const repairSet = expectedChunks;

    if (repairSet.length === 0) {
      this.logger.debug(`File healthy, skipping: path="${filePath}"`);
      return { status: 'healthy' };
    }

    if (options?.dryRun === true) {
      this.logger.info(`DRY-RUN: would repair ${repairSet.length} chunk(s): path="${filePath}"`);
      return { status: 'dry-run', wouldRepair: repairSet.length };
    }

    // 8. Re-chunk WITH enrichment (config as-is) and filter to the repair set.
    const enrichedResult = await this.chunkContentUseCase.execute({
      content,
      filePath,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
      fileHash,
      hardwareId,
    });
    if (enrichedResult.isKo()) {
      this.logger.error(
        `Failed to re-chunk with enrichment: path="${filePath}", error="${enrichedResult.getFormattedErrors()}"`,
      );
      return { status: 'error', reason: 'enriched-chunk-set-failed' };
    }

    const repairIndexes = new Set(repairSet.map(chunk => chunk.chunkIndex));
    const repairChunks = enrichedResult.getValue().filter(chunk => repairIndexes.has(chunk.chunkIndex));

    if (repairChunks.length === 0) {
      this.logger.warn(
        `Repair set vanished after enriched re-chunk (chunking drift?): path="${filePath}", expected=${repairIndexes.size}`,
      );
      return { status: 'error', reason: 'repair-set-empty-after-rechunk' };
    }

    // 9. Serialize the submit through the queue so `waitForEmpty → exit` covers
    //    all recovery work. addToQueue is called from the top-level loop — never
    //    from inside a running queued task (the queue deadlocks by design).
    //    trackMemory happens inside IngestChunkUseCase via metadata.filePath
    //    (mirrors ProcessFileUseCase.ingestFile).
    await this.processingQueue.addToQueue(async () => {
      const result = await this.ingestChunkUseCase.execute({
        chunks: repairChunks,
        sourceId: source.id,
        metadata: { filePath },
        fileHash,
        hardwareId,
        forceReembed: true,
      });
      if (result.isKo()) {
        this.logger.error(`Repair submit failed: path="${filePath}", error="${result.getFormattedErrors()}"`);
      }
    });

    this.logger.info(`Repair submitted: path="${filePath}", chunks=${repairChunks.length}`);
    return { status: 'repaired', repairedChunks: repairChunks.length };
  }

  /**
   * Full re-ingest via ProcessFileUseCase — it already enqueues itself, so no
   * extra queue wrapping here (mirrors ForceReprocessService).
   */
  private async runProcessFile(
    tracker: FileTracker,
    source: WatchSourceConfig,
    eventType: 'add' | 'change',
  ): Promise<void> {
    const result = await this.processFileUseCase.execute({
      filePath: tracker.filePath,
      eventType,
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
    });

    if (result.isKo()) {
      this.logger.error(
        `File re-ingest failed: path="${tracker.filePath}", event="${eventType}", error="${result.getFormattedErrors()}"`,
      );
    }
  }
}
