import { Injectable } from '@nestjs/common';
import fs from 'fs';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { isPathInScope } from '../glob-matcher';
import { FORCE_FORGET_ENV_VAR, MASS_FORGET_THRESHOLD } from '../mass-forget-guard';

/**
 * Outcome of a single reconciliation run.
 *
 * - sourcesChecked: watch sources iterated over.
 * - excludedMatched: tracked files found OUT OF SCOPE for their source — matched
 *   by no include pattern when one is present, or matched by an exclude pattern.
 *   (Field name kept for wire-compatibility; the generalized meaning is the
 *   out-of-scope candidate count — spec §5 EP4 / ADR-6.)
 * - skipped: out-of-scope files no longer present on disk (nothing to forget).
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
 * Startup reconciliation for scope-narrowing (exclude deny-lists and include
 * allow-lists).
 *
 * Scope configuration only prevents *future* ingestion — files already
 * ingested before a pattern was added (an exclude) or before an include
 * rollout narrowed the boundary remain in bensyne. This service walks the
 * racochu DB (the source of truth for tracked files, AD-2), re-checks every
 * tracked file against each source's effective scope, and forgets the
 * out-of-scope ones that still exist on disk.
 *
 * Semantics (AD-6):
 * - Non-fatal: a single file/source failure never blocks startup — it is
 *   logged and skipped. The service never throws for reconciliation errors.
 * - Idempotent: forgetByFile is an idempotent no-op for already-forgotten
 *   files, so running twice is safe.
 * - Mode-independent: no awareness of the run mode; the caller decides when.
 * - Never touches in-scope files.
 * - Mass-forget safeguard: refuses to forget more than MASS_FORGET_THRESHOLD
 *   files from a single source in one run unless RACOCHU_RECONCILE_FORCE_FORGET=1.
 *   The candidate set is the out-of-scope set, so include rollouts are covered
 *   by the same guard, unchanged (ADR-6).
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
   * Reconcile all watch sources: forget tracked files that are out of scope
   * for their source (include-non-matching when an include list is present,
   * or exclude-matching) and still exist on disk. Never throws; returns a
   * summary.
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
      `Reconciliation complete: sources=${summary.sourcesChecked}, outOfScope=${summary.excludedMatched}, ` +
        `forgotten=${summary.forgotten}, skipped=${summary.skipped}, failed=${summary.failed}, ` +
        `refused=${summary.refusedMassForget}`,
    );

    return summary;
  }

  /**
   * Out-of-scope predicate for a tracked path — the exact negation of the one
   * shared scope composition every enforcement point uses (isPathInScope =
   * (no include ∨ included) ∧ ¬excluded), i.e. `(include present ∧
   * !included) ∨ excluded` per spec §5 EP4 / ADR-6. Evaluated against the
   * tracked ABSOLUTE path: glob-matcher normalizes every pattern to the
   * any-depth form, so one pattern set matches this basis exactly like the
   * root-relative ones (cross-basis parity, invariant I3) — the same basis
   * this service already used for exclude matching.
   */
  private isOutOfScope(trackedPath: string, source: WatchSourceConfig): boolean {
    return !isPathInScope(trackedPath, source.include, source.exclude);
  }

  private async reconcileSource(source: WatchSourceConfig, summary: ReconciliationSummary): Promise<void> {
    const trackers = await this.fileMemoryTrackerService.findBySourceId(source.id);
    const memoryBank = source.memoryBank ?? source.id;

    // Identify files that are out of scope for this source (generalized
    // candidate set — the guard below covers include rollouts for free, ADR-6)
    const outOfScopeTrackers = trackers.filter(t => this.isOutOfScope(t.filePath, source));

    // Mass-forget safeguard: refuse if more than threshold files would be forgotten
    // without an explicit override. This prevents catastrophic patterns (e.g.
    // `**/.*/**`) or a wide include rollout from silently mass-forgetting the bank.
    if (outOfScopeTrackers.length > this.massForgetThreshold && !this.forceForget) {
      summary.refusedMassForget += 1;
      this.logger.warn(
        `MASS-FORGET REFUSED: source="${source.id}", tracked=${trackers.length}, ` +
          `outOfScopeMatched=${outOfScopeTrackers.length}, threshold=${this.massForgetThreshold}. ` +
          `Scope patterns — include: [${(source.include ?? []).join(', ')}], ` +
          `exclude: [${source.exclude.join(', ')}]. ` +
          `Set ${FORCE_FORGET_ENV_VAR}=1 to bypass this safeguard.`,
      );
      return;
    }

    // Process each out-of-scope tracker
    for (const tracker of outOfScopeTrackers) {
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
            `Failed to forget out-of-scope file; filePath="${tracker.filePath}", ` +
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
              `Failed to delete tracker for out-of-scope file; filePath="${tracker.filePath}", ` +
                `error="${(error as Error).message}"`,
            );
          }
        }
      } catch (error) {
        summary.failed += 1;
        this.logger.warn(
          `Unexpected error forgetting out-of-scope file; filePath="${tracker.filePath}", ` +
            `error="${(error as Error).message}"`,
        );
      }
    }
  }
}
