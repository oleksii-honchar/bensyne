import { Injectable } from '@nestjs/common';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { FileTrackerRepository } from '../../infrastructure/repositories/file-tracker.repository';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { ProcessFileOutcome, ProcessFileUseCase } from '../../use-cases/process-file.use-case';
import { Result } from '../../utils/result';
import { isPastDue } from '../../utils/ttl-activity';
import { isPathExcluded } from '../glob-matcher';

/**
 * Per-run classification counters for the C8 batch summary (spec C8,
 * T6; fields re-baselined by the DEC-A7 amendment, T11). Accumulated in
 * the existing batch loops from what the loop already knows; RETURNED as the
 * run's summary DATA and emitted by the public entry methods — emission is
 * SPLIT BY MODE in logBatchSummary (C8 amended):
 * - `resume finished: files=…, ingested=…, failed=…` (resume/auto-populate;
 *   the bank-verification `verified-skips` field retires from resume output
 *   with the removed verification; `files=` is the NEW-FILES-QUEUE SIZE per
 *   spec C8 literal (developer ruling 2026-11-02: the queue is the
 *   row-subtraction; activity-gate skips are downstream of the count),
 *   `ingested=` is the existing successful-execute counter, `failed=` comes
 *   from ResumeRunTally only);
 * - `force-reprocess finished: files=…, gated-skips=…, terminal-skip-skips=…,
 *   verified-skips=…, re-ingested=…` — field set UNCHANGED, `files=` keeps
 *   the per-execute-attempt v1 arithmetic (DEC-A7: force still walks
 *   everything and may legitimately see gate hits).
 * The DATA field names/shape are UNCHANGED by T11 (e2e + plan T12 assert on
 * them). Callers in main.ts keep ignoring the return value — exit-code and
 * early-exit behavior are untouched.
 */
export interface BatchRunSummary {
  /** Mode-specific by ruled design: resume/auto-populate runs count the full
   * new-files queue (spec C8 queue-size signal); force-reprocess runs count
   * execute-attempts (v1-pinned). */
  files: number;
  gatedSkips: number;
  terminalSkipSkips: number;
  verifiedSkips: number;
  reIngested: number;
}

/**
 * Internal run-scoped presentation state for the resume/auto-populate family
 * (T11 / C8 amended). The ONE counter field `failures` counts Result.ko
 * outcomes of the run so the split resume summary line can render
 * `failed=<ko count>` (same semantics as the heartbeat's `failures=` field
 * from the fixed operator field list; a source-level thrown error still
 * surfaces through its own existing 'Failed to resume source' error line and
 * is not a per-file failure). Deliberately NOT part of the returned
 * BatchRunSummary DATA — the returned object's field names/shape stay
 * exactly as before (explicit T11 constraint: e2e + T12 assert on returned
 * DATA; force-path emissions and assertions untouched).
 */
interface ResumeRunTally {
  summary: BatchRunSummary;
  failures: number;
}

/**
 * Heartbeat cadence for the batch loops (Ad-Hoc Task F — operator
 * visibility): ONE INFO progress line per this many files handled inside a
 * loop run, so a long `--resume`/`--force-reprocess` distinguishes slow
 * steady progress from a hang (payfit incident: 45+ minutes of silence
 * between "Files found for resume" and the final summary — healthy files
 * log only at DEBUG). O(corpus/100) lines; per-file volumes unchanged.
 */
const PROGRESS_HEARTBEAT_FILES = 100;

/**
 * Progress state for ONE loop run (one source enumeration) feeding the
 * heartbeat. Carries only signals the loop already has: loop-local
 * pre-branch/outcome tallies (stale-tracker, untracked, ko) plus the run's
 * BatchRunSummary reference — `verified=` and `gated=` are read as
 * loop-scoped deltas of its existing counters (no new DB reads; the summary
 * semantics and the final summary lines are untouched). Terminal skips are
 * deliberately NOT a heartbeat field (fixed operator field list); the final
 * summary remains the run's terminal artifact.
 */
interface LoopProgressState {
  prefix: 'resume progress' | 'force-reprocess progress';
  /** Files in THIS loop's queue — the heartbeat denominator. For resume that
   * is the NEW-FILES queue (T10/DEC-A7), not the raw enumeration; for the
   * force loop the full walk (unchanged). */
  total: number;
  runSummary: BatchRunSummary;
  baseVerifiedSkips: number;
  baseGatedSkips: number;
  /** Files taken through the untracked→new-file branch (loop-local). On the
   * resume loop this is every queued file by definition; the stale-repair
   * classifier was retired with the bank verification (T10/DEC-A7) — the
   * heartbeat keeps the field at structurally 0 (format string unchanged). */
  untrackedCount: number;
  /** Result.ko outcomes of THIS loop run (loop-local). */
  failureCount: number;
}

@Injectable()
export class ForceReprocessService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly processFileUseCase: ProcessFileUseCase,
    private readonly processingQueue: FileProcessingQueue,
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    // T10/DEC-A7: the resume queue-subtraction seam. Injected exactly as
    // RecoverService already injects it (recover.service.ts) — same DI token,
    // no new wiring. Never called per-file (one call per source).
    private readonly fileTrackerRepository: FileTrackerRepository,
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

  // T11: resume-family runs carry one internal ko counter next to the summary
  // for the split-line `failed=` — the returned summary object stays exactly
  // the five v1 fields (see ResumeRunTally docstring).
  private newResumeRun(): ResumeRunTally {
    return { summary: this.newBatchRunSummary(), failures: 0 };
  }

  /**
   * Classify ONE file the loop actually processed (an execute() call) into
   * the classification counters ONLY: ok-payloads carrying the additive
   * `skipped` marker split into gated vs terminal (no extra DB reads);
   * any other ok outcome is real ingest work → re-ingested; ko outcomes
   * add nothing here (their error log already names them).
   * `summary.files` is NOT touched here — its accumulation is mode-specific
   * at the loop sites (developer ruling 2026-11-02): the force loop counts
   * one per execute-attempt (v1-pinned); the resume path counts the full
   * new-files queue at queue construction (spec C8: `files=<queue size>`,
   * activity-gate skips happen downstream of the count).
   */
  private countProcessedFile(summary: BatchRunSummary, result: Result<unknown>): void {
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

  /**
   * C8 summary emission — SPLIT BY MODE (C8 AMENDED 2026-11-02 / DEC-A7,
   * plan T11). Presentation-only concern: the DATA in `summary` is
   * unchanged for every path.
   * - Resume/auto-populate: exactly `resume finished: files=…, ingested=…,
   *   failed=…`. `verified-skips` (and every other v1 field) is RETIRED from
   *   resume output — the counter retired with the bank verification T10
   *   removed. `ingested=` reuses the existing successful-execute counter
   *   (`reIngested`); `failed=` is the run-scoped ko count carried by
   *   ResumeRunTally — an internal presentation counter, never part of the
   *   returned DATA.
   * - `force-reprocess finished:` emission is UNCHANGED (full field set —
   *   force still walks everything and may legitimately see gate hits).
   */
  private logBatchSummary(
    mode: 'resume finished' | 'force-reprocess finished',
    summary: BatchRunSummary,
    resumeFailures = 0,
  ): void {
    if (mode === 'resume finished') {
      this.logger.info(
        `${mode}: files=${summary.files}, ingested=${summary.reIngested}, failed=${resumeFailures}`,
      );
      return;
    }
    this.logger.info(
      `${mode}: files=${summary.files}, gated-skips=${summary.gatedSkips}, terminal-skip-skips=${summary.terminalSkipSkips}, verified-skips=${summary.verifiedSkips}, re-ingested=${summary.reIngested}`,
    );
  }

  private newLoopProgress(
    prefix: LoopProgressState['prefix'],
    runSummary: BatchRunSummary,
  ): LoopProgressState {
    return {
      prefix,
      total: 0,
      runSummary,
      baseVerifiedSkips: runSummary.verifiedSkips,
      baseGatedSkips: runSummary.gatedSkips,
      untrackedCount: 0,
      failureCount: 0,
    };
  }

  /**
   * Heartbeat (Ad-Hoc F): called once per file the loop has finished
   * handling (every path that consumes a queue position), emitted only at
   * every PROGRESS_HEARTBEAT-th handled file. Field sources —
   * verified= loop delta of summary.verifiedSkips (structurally 0 on the
   * resume loop since T10/DEC-A7 retired the bank-verification classifier;
   * still live for any consumer that increments it); gated= loop delta of
   * summary.gatedSkips (ok outcome with skipped='unchanged'); stale-repair=
   * structurally 0 (the stale-tracker classifier was removed from the resume
   * path — the FORMAT string is unchanged per T10: "do not change the format
   * strings"; the field list stays so the operator contract holds);
   * untracked= the loop's own new-file branch count; failures= Result.ko
   * outcomes. Branch fields and outcome fields may overlap by design (a ko'd
   * queued file counts in both) — the line reads as branch provenance +
   * failure visibility, exactly per the fixed operator field list. Format is
   * the user-specified contract: `<prefix>: <processed>/<total> processed
   * (verified=…, gated=…, stale-repair=…, untracked=…, failures=…)`.
   */
  private noteLoopProgress(progress: LoopProgressState, processed: number): void {
    if (processed % PROGRESS_HEARTBEAT_FILES !== 0) {
      return;
    }
    const verified = progress.runSummary.verifiedSkips - progress.baseVerifiedSkips;
    const gated = progress.runSummary.gatedSkips - progress.baseGatedSkips;
    this.logger.info(
      `${progress.prefix}: ${processed}/${progress.total} processed (verified=${verified}, gated=${gated}, stale-repair=0, untracked=${progress.untrackedCount}, failures=${progress.failureCount})`,
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

    const run = this.newResumeRun();
    for (const source of sources) {
      await this.resumeSourceInternal(source, run);
    }
    this.logBatchSummary('resume finished', run.summary, run.failures);
    return run.summary;
  }

  async resumeSource(sourceId: string, sources: WatchSourceConfig[]): Promise<BatchRunSummary> {
    this.logger.info(`Resuming missing chunks for source; id="${sourceId}"`);

    const source = sources.find(s => s.id === sourceId);
    if (!source) {
      this.logger.error(`Source not found; id="${sourceId}"`);
      return this.newBatchRunSummary();
    }

    const run = this.newResumeRun();
    await this.resumeSourceInternal(source, run);
    this.logBatchSummary('resume finished', run.summary, run.failures);
    return run.summary;
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
    const run = this.newResumeRun();
    for (const source of targets) {
      this.logger.info(`Auto-populating source: id="${source.id}", path="${source.path}"`);
      await this.resumeSourceInternal(source, run);
    }
    // Spec §9 (amended): the auto-populate pass IS a resume pass and its
    // flat C8 summary across manual watch starts is the acceptance signal —
    // including the T11 split-line format and its internal ko counter.
    this.logBatchSummary('resume finished', run.summary, run.failures);
    return run.summary;
  }

  /**
   * Resume/auto-populate queue (C4 AMENDED 2026-11-02 per DEC-A7): NEW FILES
   * ONLY. `known` = every file with a FileTracker row for this source —
   * normally-ingested OR terminal-skip rows alike (a row is a row). ONE
   * findTrackedBySourceId call per source, never per file; the queue is a
   * pure set subtraction — no per-file hash, no bank call, no tracker read
   * for known files (a repeat run on a steady corpus is free: files=0).
   *
   * RETIRED here (moved to --recover — the sole reconciler, DEC-A7 (a)/(b)/
   * (c)): the per-file getMemoryIds pre-read, the bank-verification block
   * (getFileChunks/isFileHealthy + isKo() defensive skip + verifiedSkips
   * counting) and the stale-tracker branch. `forceIngest:false` is passed
   * explicitly: the internal hash-gate is structurally unreachable on this
   * path (no row ⇒ no stored hash) but is KEPT as defense-in-depth per the
   * DEC-A3 amendment / DEC-A7 Rejected-list, pinned by unit test.
   */
  private async resumeSourceInternal(source: WatchSourceConfig, run: ResumeRunTally): Promise<void> {
    const summary = run.summary;
    try {
      const files = await this.getFiles(source);
      this.logger.info(
        `Files found for resume: source="${source.id}", path="${source.path}", count=${files.length}`,
      );

      // Spec §3 C4 (verbatim contract): build `known` from one per-source
      // row fetch and subtract. Any row (normal OR terminal-skip) = known.
      const known = new Set(
        (await this.fileTrackerRepository.findTrackedBySourceId(source.id)).map(row => row.filePath),
      );
      const newFiles = files.filter(file => !known.has(file));

      // Mode-specific `files` accumulation (spec C8 literal; developer ruling
      // 2026-11-02): the resume path counts the FULL NEW-FILES QUEUE at
      // construction — an activity-gate skip happens downstream of the count,
      // so expired-but-queued files stay part of files= (health signal: the
      // repeat-run signature remains files=0 on an emptied queue).
      summary.files += newFiles.length;

      // Ad-Hoc F heartbeat: per-loop progress state over THIS queue run;
      // all fields come from signals the loop already has (see noteLoopProgress).
      const progress = this.newLoopProgress('resume progress', summary);
      progress.total = newFiles.length;

      // Queue visibility at zero per-file cost (the C7/G5 repeat-run story:
      // known files are excluded here, never enumerated into the loop).
      this.logger.info(
        `Resume queue built: source="${source.id}", enumerated=${files.length}, known=${known.size}, new=${newFiles.length}`,
      );

      // [i/totalFilesInQueue] is the 1-based position in the NEW-FILES queue
      // (not a stored index; row-known files consume no position).
      const totalFilesInQueue = newFiles.length;
      for (let i = 0; i < newFiles.length; i++) {
        const file = newFiles[i];
        const position = i + 1;

        // B14(a) activity gate (opt-in per source, spec §3.1): a past-due file
        // is not eligible for batch paths at all — skip before any ingest
        // work (behavior preserved from before T10; now evaluated on the
        // new-files queue).
        if (source.ttlDays != null && (await this.isFilePastDue(file, source.ttlDays))) {
          this.logger.info(
            `Skipping activity-expired file [${position}/${totalFilesInQueue}]: path="${file}"`,
          );
          this.noteLoopProgress(progress, position);
          continue;
        }

        // Every file still here is an un-known (new) file: the single branch
        // of the queue (Ad-Hoc F untracked= field source).
        progress.untrackedCount += 1;
        this.logger.info(`Resuming new file [${position}/${totalFilesInQueue}]: path="${file}"`);

        const result = await this.processFileUseCase.execute({
          filePath: file,
          eventType: 'add',
          sourceId: source.id,
          memoryBank: source.memoryBank,
          sourceConfig: source,
          // Explicit false (AC4 defense-in-depth pin): the gate decision
          // belongs to ProcessFileUseCase; nothing here has proven a repair.
          forceIngest: false,
        });

        this.countProcessedFile(summary, result);

        if (result.isKo()) {
          // Ad-Hoc F field source: failures of this loop run (ko outcomes).
          progress.failureCount += 1;
          // T11: run-scoped ko tally feeding the split resume line's `failed=`
          // (internal presentation counter — never part of returned DATA).
          run.failures += 1;
          this.logger.error(`File resume failed: path="${file}", error="${result.getFormattedErrors()}"`);
        }
        this.noteLoopProgress(progress, position);
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

      // Ad-Hoc F heartbeat mirror for the force-reprocess/process-only loop.
      // This loop has no pre-branch classifications, so verified/stale/untracked
      // stay 0 by construction — the field LIST is the fixed contract (documented
      // reading of "batch loops", plural), gated/failures come from outcomes.
      const progress = this.newLoopProgress('force-reprocess progress', summary);
      progress.total = files.length;

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

        // Mode-specific `files` accumulation (ruling 2026-11-02): the force
        // path counts ONE per execute-attempt (v1-pinned semantics, byte-
        // identical to the previous shared counter).
        summary.files += 1;
        this.countProcessedFile(summary, result);

        if (result.isKo()) {
          // Ad-Hoc F field source: failures of this loop run (ko outcomes).
          progress.failureCount += 1;
          this.logger.error(
            `File reprocessing failed [${position}/${totalFilesInQueue}]: path="${file}", error="${result.getFormattedErrors()}"`,
          );
        }
        this.noteLoopProgress(progress, position);
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
