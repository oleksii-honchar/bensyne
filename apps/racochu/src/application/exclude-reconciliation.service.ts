import { Injectable } from '@nestjs/common';
import fs from 'fs';
import { WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { isPathExcluded } from './glob-matcher';

/**
 * Outcome of a single reconciliation run.
 *
 * - sourcesChecked: watch sources iterated over.
 * - excludedMatched: tracked files that match a source exclude pattern.
 * - skipped: excluded files no longer present on disk (nothing to forget).
 * - forgotten: files for which forgetByFile was called and returned ok.
 * - failed: files for which forgetByFile returned ko (logged, non-fatal).
 */
export interface ReconciliationSummary {
  sourcesChecked: number;
  excludedMatched: number;
  skipped: number;
  forgotten: number;
  failed: number;
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
 */
@Injectable()
export class ExcludeReconciliationService {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly fileMemoryTrackerService: FileMemoryTrackerService,
    private readonly bensyneClient: BensyneClient,
    private readonly configurationService: ConfigurationService,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'ExcludeReconciliationService' });
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
        `forgotten=${summary.forgotten}, skipped=${summary.skipped}, failed=${summary.failed}`,
    );

    return summary;
  }

  private async reconcileSource(source: WatchSourceConfig, summary: ReconciliationSummary): Promise<void> {
    const trackers = await this.fileMemoryTrackerService.findBySourceId(source.id);
    const excludePatterns = source.exclude ?? [];
    const memoryBank = source.memoryBank ?? source.id;

    for (const tracker of trackers) {
      if (!isPathExcluded(tracker.filePath, excludePatterns)) {
        continue;
      }

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
          summary.forgotten += 1;
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
