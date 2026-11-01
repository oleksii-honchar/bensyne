import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { ProcessFileOutcome, ProcessFileUseCase } from '../../use-cases/process-file.use-case';
import { Result } from '../../utils/result';
import { isPastDue } from '../../utils/ttl-activity';
import { isPathExcluded } from '../glob-matcher';
import { isFileHealthy } from '../utils/file-health';

/**
 * Per-run classification counters for the C8 batch summary line (spec C8,
 * T6). Accumulated in the existing batch loops from what the loop already
 * knows; emitted by the public entry methods as
 * `<mode> finished: files=…, gated-skips=…, terminal-skip-skips=…,
 * verified-skips=…, re-ingested=…` and returned as the run's summary DATA
 * (callers in main.ts keep ignoring the return value — exit-code and
 * early-exit behavior are untouched).
 */
export interface BatchRunSummary {
  files: number;
  gatedSkips: number;
  terminalSkipSkips: number;
  verifiedSkips: number;
  reIngested: number;
}

@Injectable()
export class ForceReprocessService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly processingQueue: FileProcessingQueue,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ForceReprocessService' });
  }

  // C8 (T6) summary primitives — zero-value summaries are logged too: a
  // FLAT summary across repeated manual starts IS the acceptance signal
  // (spec §9 amended), so it only works if quiet runs say so explicitly.
  private newBatchRunSummary(): BatchRunSummary {
    return { files: 0, gatedSkips: 0, terminalSkipSkips: 0, verifiedSkips: 0, reIngested: 0 };
  }

  /**
   * Classify ONE file the loop actually processed (an execute() call):
   * `files` counts every processed file; ok-payloads carrying the additive
   * `skipped` marker split into gated vs terminal (no extra DB reads);
   * any other ok outcome is real ingest work → re-ingested; ko outcomes
   * are counted in `files` only (their error log already names them).
   */
  private countProcessedFile(summary: BatchRunSummary, result: Result<unknown>): void {
    summary.files += 1;
    if (result.isKo()) {
      return;
    }
    const outcome = result.getValue() as ProcessFileOutcome | undefined;
    if (outcome?.skipped === 'unchanged') {
      summary.gatedSkips += 1;
      return;
    }
    if (outcome?.skipped === 'terminal') {
      summary.terminalSkipSkips += 1;
      return;
    }
    summary.reIngested += 1;
  }

  private logBatchSummary(
    mode: 'resume finished' | 'force-reprocess finished',
    summary: BatchRunSummary,
  ): void {
    this.logger.info(
      `${mode}: files=${summary.files}, gated-skips=${summary.gatedSkips}, terminal-skip-skips=${summary.terminalSkipSkips}, verified-skips=${summary.verifiedSkips}, re-ingested=${summary.reIngested}`,
    );
  }

  // `forceIngest` (C4/DEC-A3): true = deliberate override — bypass the
  // ProcessFileUseCase hash gate; false = gated walk. Force-reprocess modes
  // default to true (their documented operator-override semantics, DEC-A6);
  // the --process-only dispatch passes false explicitly (main.ts).
  async forceReprocessAll(
    sources: WatchSourceConfig[],
    opts: { forceIngest: boolean } = { forceIngest: true },
  ): Promise<BatchRunSummary> {
    this.logger.info(`Force reprocessing all sources: count=${sources.length}`);

    const summary = this.newBatchRunSummary();
    for (const source of sources) {
      await this.processSource(source, opts, summary);
    }
    this.logBatchSummary('force-reprocess finished', summary);
    return summary;
  }

  async forceReprocessSource(
    sourceId: string,
    sources: WatchSourceConfig[],
    opts: { forceIngest: boolean } = { forceIngest: true },
  ): Promise<BatchRunSummary> {
    this.logger.info(`Force reprocessing source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      // Early exit untouched: no run happened, so NO summary is logged — an
      // empty summary value is returned only for the type's totalness.
      return this.newBatchRunSummary();
    }

    const summary = this.newBatchRunSummary();
    await this.processSource(source, opts, summary);
    this.logBatchSummary('force-reprocess finished', summary);
    return summary;
  }

  async resumeAll(sources: WatchSourceConfig[]): Promise<BatchRunSummary> {
    this.logger.info(`Resuming missing chunks for all sources: count=${sources.length}`);

    const summary = this.newBatchRunSummary();
    for (const source of sources) {
      await this.resumeSourceInternal(source, summary);
    }
    this.logBatchSummary('resume finished', summary);
    return summary;
  }

  async resumeSource(sourceId: string, sources: WatchSourceConfig[]): Promise<BatchRunSummary> {
    this.logger.info(`Resuming missing chunks for source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return this.newBatchRunSummary();
    }

    const summary = this.newBatchRunSummary();
    await this.resumeSourceInternal(source, summary);
    this.logBatchSummary('resume finished', summary);
    return summary;
  }

  async forceReprocessFile(
    filePath: string,
    source: WatchSourceConfig,
    opts: { forceIngest: boolean } = { forceIngest: true },
  ): Promise<void> {
    this.logger.info(`Force reprocessing single file; path="${filePath}", source="${source.id}"`);

    const result = await this.processFileUseCase.execute({
      filePath,
      eventType: 'add',
      sourceId: source.id,
      memoryBank: source.memoryBank,
      sourceConfig: source,
      forceIngest: opts.forceIngest,
    });

    if (result.isKo()) {
      this.logger.error(
        `File reprocessing failed: path="${filePath}", error="${result.getFormattedErrors()}"`,
      );
    }
  }

  /** Startup population: resume only sources that have not opted out. */
  async autoPopulateSources(sources: WatchSourceConfig[]): Promise<BatchRunSummary> {
    const targets = sources.filter(s => s.autoPopulate !== false);
    const summary = this.newBatchRunSummary();
    for (const source of targets) {
      this.logger.info(`Auto-populating source: id="${source.id}", path="${source.path}"`);
      await this.resumeSourceInternal(source, summary);
    }
    // Spec §9 (amended): the auto-populate pass IS a resume pass and its
    // flat C8 summary across manual watch starts is the acceptance signal.
    this.logBatchSummary('resume finished', summary);
    return summary;
  }

  private async resumeSourceInternal(source: WatchSourceConfig, summary: BatchRunSummary): Promise<void> {
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for resume: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      // [i/totalFilesInQueue] is the 1-based queue position (not a stored index).
      const totalFilesInQueue = files.length;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const position = i + 1;

        // B14(a) activity gate (opt-in per source, spec §3.1): a past-due file
        // is not eligible for batch paths at all — skip before any
        // getMemoryIds/verify/ingest work, tracked or never-tracked alike.
        if (source.ttlDays != null && (await this.isFilePastDue(file, source.ttlDays))) {
          this.logger.info(
            `Skipping activity-expired file [${position}/${totalFilesInQueue}]: path="${file}"`,
          );
          continue;
        }

        let memoryIds: string[];
        try {
          memoryIds = await this.fileMemoryTrackerService.getMemoryIds(file);
        } catch (error) {
          this.logger.warn(
            `Skipping file for resume; failed to read stored memory count [${position}/${totalFilesInQueue}]: path="${file}", error="${error instanceof Error ? error.message : String(error)}"`,
          );
          continue;
        }

        // Bank-verified skip: the tracker can be stale (e.g. bank wiped) — a
        // file with tracked memories is verified against the bank before being
        // trusted as complete (mirrors RecoverService.recoverFile).
        if (memoryIds.length > 0) {
          const chunksResult = await this.bensyneClient.getFileChunks(file, source.memoryBank);
          if (chunksResult.isKo()) {
            // Bank read failed (MCP down / error). Skip defensively — never
            // re-ingest on a transient failure (duplicate-memory risk);
            // --recover remains the guaranteed reconciliation tool.
            this.logger.warn(
              `Bank read error for resume [${position}/${totalFilesInQueue}]: path="${file}", error="${chunksResult.getFormattedErrors()}" — skipping (preserving existing memories)`,
            );
            continue;
          }

          const fileChunks = chunksResult.getValue();

          if (isFileHealthy(fileChunks)) {
            // C8 (T6): loop-level classification — a bank-verified healthy
            // file never reaches execute(); it is counted as a verified skip.
            summary.verifiedSkips += 1;
            this.logger.debug(
              `Skipping verified file for resume [${position}/${totalFilesInQueue}]: path="${file}", memories="${memoryIds.length}"`,
            );
            continue;
          }

          this.logger.info(
            `Resuming stale-tracker file (absent from bank) [${position}/${totalFilesInQueue}]: path="${file}"`,
          );
        } else {
          this.logger.info(`Resuming untracked file [${position}/${totalFilesInQueue}]: path="${file}"`);
        }

        // C4/DEC-A3 split of the shared execute path (only reachable past the
        // verified-healthy and bank-error skips): memoryIds.length > 0 here
        // means the stale-tracker branch — bank verification already proved
        // the memories lost, so the hash gate must not veto the repair (G3).
        // Untracked files stay gated (false): the hash gate + skip-rows stop
        // the M2 retry loop at zero bank/LLM cost.
        const forceReingest = memoryIds.length > 0;

        const result = await this.processFileUseCase.execute({
          filePath: file,
          eventType: 'add',
          sourceId: source.id,
          memoryBank: source.memoryBank,
          sourceConfig: source,
          forceIngest: forceReingest,
        });

        this.countProcessedFile(summary, result);

        if (result.isKo()) {
          this.logger.error(`File resume failed: path="${file}", error="${result.getFormattedErrors()}"`);
        }
      }
    } catch (error) {
      this.logger.error(
        `Failed to resume source: id="${source.id}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }
  }

  /**
   * B14(a) gate call for one enumerated file. A successful stat makes mtime the
   * authoritative activity clock, which short-circuits the helper's required
   * row fields (the placeholder is never read) — so the same call shape is
   * correct for tracked and never-tracked files (OD-5 uniformity). The clock
   * rule lives ONLY in isPastDue. A stat error means activity is not
   * observable here: treat as not past due and fall through to today's path.
   */
  private async isFilePastDue(filePath: string, ttlDays: number): Promise<boolean> {
    try {
      const stat = await fs.stat(filePath);
      const now = Date.now();
      return isPastDue({ mtimeMs: stat.mtimeMs, rowCreatedAt: new Date(now), ttlDays }, now);
    } catch {
      return false;
    }
  }

  private async processSource(
    source: WatchSourceConfig,
    opts: { forceIngest: boolean },
    summary: BatchRunSummary,
  ): Promise<void> {
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for reprocessing: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      // Execute directly — execute() → executeInternal() → addToQueue() already
      // serializes via the queue. Awaiting keeps processing strictly sequential.
      // [i/totalFilesInQueue] is the 1-based queue position (not a stored index).
      const totalFilesInQueue = files.length;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const position = i + 1;

        this.logger.info(`Processing file [${position}/${totalFilesInQueue}]: path="${file}"`);

        const result = await this.processFileUseCase.execute({
          filePath: file,
          eventType: 'add',
          sourceId: source.id,
          memoryBank: source.memoryBank,
          sourceConfig: source,
          forceIngest: opts.forceIngest,
        });

        this.countProcessedFile(summary, result);

        if (result.isKo()) {
          this.logger.error(
            `File reprocessing failed [${position}/${totalFilesInQueue}]: path="${file}", error="${result.getFormattedErrors()}"`,
          );
        }
      }
    } catch (error) {
      this.logger.error(
        `Failed to process source: id="${source.id}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }
  }

  /**
   * R1: enumerate ALL declared roots of the source (`resolvedPaths`; a
   * single-`path` source carries the normalized `[path]` shape, so its file
   * set and order are identical to before). Union across roots, declared-root
   * order, de-duplicated by resolved absolute path — same-named files under
   * DIFFERENT roots stay distinct entries.
   */
  private async getFiles(source: WatchSourceConfig): Promise<string[]> {
    const merged: string[] = [];
    const seen = new Set<string>();

    for (const rootPath of this.declaredRoots(source)) {
      const rootFiles = await this.scanRoot(rootPath, source);
      for (const file of rootFiles) {
        const key = path.resolve(file);
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(file);
        }
      }
    }

    return merged;
  }

  /** Resolved, de-duplicated root paths in declared order. */
  private declaredRoots(source: WatchSourceConfig): string[] {
    const declared = source.resolvedPaths ?? [source.path];
    const roots: string[] = [];
    for (const rootPath of declared) {
      const resolved = this.resolvePath(rootPath);
      if (!roots.includes(resolved)) {
        roots.push(resolved);
      }
    }
    return roots;
  }

  private async scanRoot(resolvedRoot: string, source: WatchSourceConfig): Promise<string[]> {
    try {
      const stats = await fs.stat(resolvedRoot);
      if (!stats.isDirectory()) {
        this.logger.warn(`Source path is not a directory; "${resolvedRoot}"`);
        return [];
      }

      return this.scanDirectory(resolvedRoot, source, resolvedRoot);
    } catch (error) {
      this.logger.error(
        `Failed to stat source path: "${resolvedRoot}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
      return [];
    }
  }

  private async scanDirectory(
    dirPath: string,
    source: WatchSourceConfig,
    sourceRoot: string,
  ): Promise<string[]> {
    const files: string[] = [];

    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry.name);
        // Exclude globs match per-root relative paths — the same semantics a
        // single-root source gets today, applied independently to each root.
        const relPath = path.relative(sourceRoot, fullPath);

        if (entry.isDirectory()) {
          // Skip excluded directories using the shared glob matcher.
          if (isPathExcluded(relPath, source.exclude)) {
            continue;
          }
          const subFiles = await this.scanDirectory(fullPath, source, sourceRoot);
          files.push(...subFiles);
        } else if (entry.isFile()) {
          if (!isPathExcluded(relPath, source.exclude)) {
            files.push(fullPath);
          }
        }
      }
    } catch (error) {
      this.logger.warn(
        `Failed to read directory: "${dirPath}", error="${error instanceof Error ? error.message : String(error)}"`,
      );
    }

    return files;
  }

  private resolvePath(filePath: string): string {
    if (filePath.startsWith('~')) {
      return path.join(os.homedir(), filePath.slice(1));
    }
    return path.resolve(filePath);
  }
}
