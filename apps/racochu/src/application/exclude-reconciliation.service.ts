import { Injectable } from '@nestjs/common';
import fs from 'fs';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { isPathExcluded } from './glob-matcher';

// Mass-forget safeguard configuration.
//
// A single reconciliation run should NEVER forget more than this many files from
// a single source without an explicit override. This protects against catastrophic
// exclude patterns (e.g. `**/.*/**` that match the whole watch root) from silently
// mass-forgetting the bank.
//
// Override: set RACOCHU_RECONCILE_FORCE_FORGET=1 to bypass the guard.
const MASS_FORGET_THRESHOLD = 20;
const FORCE_FORGET_ENV_VAR = 'RACOCHU_RECONCILE_FORCE_FORGET';

/**
 * Outcome of a single reconciliation run.
 *
 * - sourcesChecked: watch sources iterated over.
 * - excludedMatched: tracked files that match a source exclude pattern.
 * - skipped: excluded files no longer present on disk (nothing to forget).
 * - forgotten: files for which forgetByFile returned ok AND the racochu tracker
 *   rows were deleted successfully.
 * - failed: files for which forgetByFile returned ko, or whose tracker cleanup
 *   (deleteByFilePath) threw (logged, non-fatal).
 * - refusedMassForget: sources where the mass-forget guard triggered (toForget >
 *   threshold) and the guard refused to proceed without an explicit override.
 */
export interface ReconciliationSummary {
  sourcesChecked: number;
  excludedMatched: number;
  skipped: number;
  forgotten: number;
  failed: number;
  refusedMassForget: number;
}

/**
 * Startup reconciliation for exclude patterns.
 *
 * Excludes only prevent *future* ingestion — files already ingested before a
 * pattern was added remain in bensyne. This service walks the racochu DB
 * (the source of truth for tracked files, AD-2), re-checks every tracked file
 * against each source's effective exclude patterns, and forgets the excluded
 * ones that still exist on disk.
 *
 * Semantics (AD-6):
 * - Non-fatal: a single file/source failure never blocks startup — it is
 *   logged and skipped. The service never throws for reconciliation errors.
 * - Idempotent: forgetByFile is an idempotent no-op for already-forgotten
 *   files, so running twice is safe.
 * - Mode-independent: no awareness of the run mode; the caller decides when.
 * - Never touches non-excluded files.
 * - Mass-forget safeguard: refuses to forget more than MASS_FORGET_THRESHOLD
 *   files from a single source in one run unless RACOCHU_RECONCILE_FORCE_FORGET=1.
 */
@Injectable()
export class ExcludeReconciliationService {
  private readonly logger: BasePinoLogger;
  private readonly forceForget: boolean;
  private readonly massForgetThreshold: number;

  constructor(
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    private readonly configurationService: ConfigurationService,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ExcludeReconciliationService' });
    this.forceForget = process.env[FORCE_FORGET_ENV_VAR] === '1';
    this.massForgetThreshold = MASS_FORGET_THRESHOLD;
  }

  /**
   * Reconcile all watch sources: forget tracked files that match exclude
   * patterns and still exist on disk. Never throws; returns a summary.
   */
  async run(): Promise<ReconciliationSummary> {
    const summary: ReconciliationSummary = {
      sourcesChecked: 0,
      excludedMatched: 0,
      skipped: 0,
      forgotten: 0,
      failed: 0,
      refusedMassForget: 0,
    };

    let sources;
    try {
      sources = this.configurationService.getWatchSources();
    } catch (error) {
      this.logger.error(`Failed to load watch sources; skipping reconciliation: ${(error as Error).message}`);
      return summary;
    }

    for (const source of sources) {
      summary.sourcesChecked += 1;
      try {
        await this.reconcileSource(source, summary);
      } catch (error) {
        // A broken source must not block reconciliation of the others.
        this.logger.error(
          `Reconciliation failed for source; id="${source.id}", error="${(error as Error).message}"`,
        );
      }
    }

    this.logger.info(
      `Reconciliation complete: sources=${summary.sourcesChecked}, excluded=${summary.excludedMatched}, ` +
        `forgotten=${summary.forgotten}, skipped=${summary.skipped}, failed=${summary.failed}, ` +
        `refused=${summary.refusedMassForget}`,
    );

    return summary;
  }

  private async reconcileSource(source: WatchSourceConfig, summary: ReconciliationSummary): Promise<void> {
    const trackers = await this.fileMemoryTrackerService.findBySourceId(source.id);
    const excludePatterns = source.exclude ?? [];
    const memoryBank = source.memoryBank ?? source.id;

    // Identify files that match exclude patterns
    const excludedTrackers = trackers.filter(t => isPathExcluded(t.filePath, excludePatterns));

    // Mass-forget safeguard: refuse if more than threshold files would be forgotten
    // without an explicit override. This prevents catastrophic patterns (e.g.
    // `**/.*/**`) from silently mass-forgetting the bank.
    if (excludedTrackers.length > this.massForgetThreshold && !this.forceForget) {
      summary.refusedMassForget += 1;
      this.logger.warn(
        `MASS-FORGET REFUSED: source="${source.id}", tracked=${trackers.length}, ` +
          `excludedMatched=${excludedTrackers.length}, threshold=${this.massForgetThreshold}. ` +
          `Offending patterns: [${excludePatterns.join(', ')}]. ` +
          `Set ${FORCE_FORGET_ENV_VAR}=1 to bypass this safeguard.`,
      );
      return;
    }

    // Process each excluded tracker
    for (const tracker of excludedTrackers) {
      summary.excludedMatched += 1;

      if (!fs.existsSync(tracker.filePath)) {
        summary.skipped += 1;
        continue;
      }

      try {
        const result = await this.bensyneClient.forgetByFile(tracker.filePath, memoryBank);
        if (result.isKo()) {
          summary.failed += 1;
          this.logger.warn(
            `Failed to forget excluded file; filePath="${tracker.filePath}", ` +
              `memoryBank="${memoryBank}", error="${result.getErrors()[0].message}"`,
          );
        } else {
          // Spec 3.3 step 3: once bensyne has forgotten the file, remove the
          // racochu tracker rows (Prisma cascade removes FileTracker +
          // FileMemoryTracker). Cleanup failure is non-fatal: count it as
          // failed and continue — the service never throws.
          try {
            await this.fileMemoryTrackerService.deleteByFilePath(tracker.filePath);
            summary.forgotten += 1;
          } catch (error) {
            summary.failed += 1;
            this.logger.warn(
              `Failed to delete tracker for excluded file; filePath="${tracker.filePath}", ` +
                `error="${(error as Error).message}"`,
            );
          }
        }
      } catch (error) {
        summary.failed += 1;
        this.logger.warn(
          `Unexpected error forgetting excluded file; filePath="${tracker.filePath}", ` +
            `error="${(error as Error).message}"`,
        );
      }
    }
  }
}
