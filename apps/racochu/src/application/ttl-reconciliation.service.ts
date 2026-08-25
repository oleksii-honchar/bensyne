import { Injectable, OnApplicationShutdown } from '@nestjs/common';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { FORCE_FORGET_ENV_VAR, MASS_FORGET_THRESHOLD } from './mass-forget-guard';

const MS_PER_DAY = 86_400_000;
// One day (24h) expressed as the daily sweep interval.
const DAILY_SWEEP_INTERVAL_MS = MS_PER_DAY;

/**
 * Outcome of a single TTL sweep run.
 *
 * - sourcesChecked: watch sources with a ttlDays that were iterated over.
 * - expired: trackers initially matched as TTL-expired (counted before the
 *   mass-forget guard, per source).
 * - wouldForget: trackers that would be forgotten (dry-run only).
 * - forgotten: trackers for which forgetByFile returned ok AND the racochu
 *   tracker rows were deleted successfully.
 * - failed: trackers for which forgetByFile returned ko, or whose tracker
 *   cleanup (deleteByFilePath) threw (logged, non-fatal).
 * - refusedMassForget: sources where the mass-forget guard triggered
 *   (expired > threshold) and refused to proceed without an override.
 * - dryRun: whether the run was a dry run (no forgets performed).
 */
export interface TtlSweepSummary {
  sourcesChecked: number;
  expired: number;
  wouldForget: number;
  forgotten: number;
  failed: number;
  refusedMassForget: number;
  dryRun: boolean;
}

/**
 * TTL reconciliation for watch sources with a `ttlDays` retention.
 *
 * Per source with a ttlDays configured, the service forgets files whose
 * tracker was created strictly before `now - ttlDays` (cutoff) through the
 * bensyne MCP `forgetFile` tool, then deletes the racochu tracker rows.
 *
 * Semantics (AD-6), mirroring ExcludeReconciliationService:
 * - Non-fatal: a single file/source failure never blocks the sweep — it is
 *   logged and skipped. The service never throws for sweep errors.
 * - Idempotent: forgetByFile is an idempotent no-op for already-forgotten
 *   files, so running twice is safe.
 * - Mode-independent: no awareness of the run mode; the caller decides when.
 * - Never touches sources without a ttlDays configured.
 * - Mass-forget safeguard: refuses to forget more than MASS_FORGET_THRESHOLD
 *   files from a single source in one run unless RACOCHU_RECONCILE_FORCE_FORGET=1.
 */
@Injectable()
export class TtlReconciliationService implements OnApplicationShutdown {
  private readonly logger: BasePinoLogger;
  private readonly forceForget: boolean;
  private readonly massForgetThreshold: number;
  private dailySweepTimer: NodeJS.Timeout | null = null;

  constructor(
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    private readonly configurationService: ConfigurationService,
    private readonly processingQueue: FileProcessingQueue,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'TtlReconciliationService' });
    this.forceForget = process.env[FORCE_FORGET_ENV_VAR] === '1';
    this.massForgetThreshold = MASS_FORGET_THRESHOLD;
  }

  /**
   * Sweep all watch sources with a ttlDays (or a single source when sourceId
   * is given): forget TTL-expired files and clean up racochu trackers.
   * Never throws; returns a summary.
   */
  async run(dryRun = false, sourceId?: string): Promise<TtlSweepSummary> {
    const summary: TtlSweepSummary = {
      sourcesChecked: 0,
      expired: 0,
      wouldForget: 0,
      forgotten: 0,
      failed: 0,
      refusedMassForget: 0,
      dryRun,
    };

    let sources: WatchSourceConfig[];
    try {
      sources = this.configurationService.getWatchSources();
    } catch (error) {
      this.logger.error(`Failed to load watch sources; skipping TTL sweep: ${(error as Error).message}`);
      return summary;
    }

    // Only sources with a ttlDays are eligible; scope by sourceId when provided.
    const eligibleSources = sources.filter(source => {
      if (source.ttlDays === undefined) {
        return false;
      }
      return sourceId === undefined || source.id === sourceId;
    });

    for (const source of eligibleSources) {
      summary.sourcesChecked += 1;
      try {
        await this.sweepSource(source, summary, dryRun);
      } catch (error) {
        // A broken source must not block the sweep of the others.
        this.logger.error(
          `TTL sweep failed for source; id="${source.id}", error="${(error as Error).message}"`,
        );
      }
    }

    this.logger.info(
      `TTL sweep complete: sources=${summary.sourcesChecked}, expired=${summary.expired}, ` +
        `forgotten=${summary.forgotten}, wouldForget=${summary.wouldForget}, ` +
        `failed=${summary.failed}, refused=${summary.refusedMassForget}, dryRun=${dryRun}`,
    );

    return summary;
  }

  /**
   * Start the daily TTL sweep interval (used in watch mode). The interval is
   * unref'd so it never keeps the process alive on its own.
   */
  startDailySweep(): void {
    this.dailySweepTimer = setInterval(async () => {
      try {
        await this.processingQueue.waitForEmpty();
        await this.run();
      } catch (error) {
        this.logger.error(
          `Daily TTL sweep failed: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }, DAILY_SWEEP_INTERVAL_MS);

    // Don't keep the event loop alive for the daily sweep.
    this.dailySweepTimer.unref?.();
  }

  /**
   * Stop the daily sweep interval.
   */
  stop(): void {
    this.clearDailySweepTimer();
  }

  /**
   * Clear the daily sweep interval on application shutdown.
   */
  onApplicationShutdown(): void {
    this.clearDailySweepTimer();
  }

  private async sweepSource(
    source: WatchSourceConfig,
    summary: TtlSweepSummary,
    dryRun: boolean,
  ): Promise<void> {
    const ttlDays = source.ttlDays as number;
    const cutoff = new Date(Date.now() - ttlDays * MS_PER_DAY);
    const trackers = await this.fileMemoryTrackerService.findExpiredBySourceId(source.id, cutoff);
    const memoryBank = source.memoryBank ?? source.id;

    // Count expired BEFORE the mass-forget guard (per the spec).
    summary.expired += trackers.length;

    if (trackers.length > this.massForgetThreshold && !this.forceForget) {
      summary.refusedMassForget += 1;
      this.logger.warn(
        `MASS-FORGET REFUSED: source="${source.id}", expired=${trackers.length}, ` +
          `threshold=${this.massForgetThreshold}. Set ${FORCE_FORGET_ENV_VAR}=1 to bypass this safeguard.`,
      );
      return;
    }

    for (const tracker of trackers) {
      // Re-read the tracker immediately before forgetting: the aggregate is
      // timestamp-free, so re-fetch createdAt from the repository and re-check
      // expiry. Skip if it no longer exists or is no longer expired.
      const createdAt = await this.fileMemoryTrackerService.getTrackerCreatedAt(tracker.filePath);
      if (createdAt === null || !(createdAt.getTime() < cutoff.getTime())) {
        continue;
      }

      if (dryRun) {
        summary.wouldForget += 1;
        continue;
      }

      try {
        const result = await this.bensyneClient.forgetByFile(tracker.filePath, memoryBank);
        if (result.isKo()) {
          summary.failed += 1;
          this.logger.warn(
            `Failed to forget TTL-expired file; filePath="${tracker.filePath}", ` +
              `memoryBank="${memoryBank}", error="${result.getErrors()[0].message}"`,
          );
        } else {
          // Once bensyne has forgotten the file, remove the racochu tracker
          // rows. Cleanup failure is non-fatal: count as failed and continue.
          try {
            await this.fileMemoryTrackerService.deleteByFilePath(tracker.filePath);
            summary.forgotten += 1;
          } catch (error) {
            summary.failed += 1;
            this.logger.warn(
              `Failed to delete tracker for TTL-expired file; filePath="${tracker.filePath}", ` +
                `error="${(error as Error).message}"`,
            );
          }
        }
      } catch (error) {
        summary.failed += 1;
        this.logger.warn(
          `Unexpected error forgetting TTL-expired file; filePath="${tracker.filePath}", ` +
            `error="${(error as Error).message}"`,
        );
      }
    }
  }

  private clearDailySweepTimer(): void {
    if (this.dailySweepTimer) {
      clearInterval(this.dailySweepTimer);
      this.dailySweepTimer = null;
    }
  }
}
