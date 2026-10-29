import type { Stats } from 'fs';
import * as fsPromises from 'fs/promises';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { aConfigService, aSourceConfig } from '../../infrastructure/config/configuration.service.test-utils';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { aFileMemoryTracker } from '../../infrastructure/repositories/file-memory-tracker.repository.test-utils';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { aBensyneClientService } from '../../infrastructure/services/bensyne-client.test-utils';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { aFileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service.test-utils';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { aFileProcessingQueueService } from '../../infrastructure/services/file-processing-queue.test-utils';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { TtlReconciliationService } from './ttl-reconciliation.service';

jest.mock('fs/promises');
const fsMock = fsPromises as jest.Mocked<typeof fsPromises>;

const MS_PER_DAY = 86_400_000;

// Fixed system time for the activity-clock matrix (exact-boundary control).
const FIXED_NOW = Date.parse('2026-10-28T12:00:00.000Z');

function aFileStatWithMtimeMs(mtimeMs: number): Stats {
  return { mtimeMs, isFile: () => true, isDirectory: () => false } as unknown as Stats;
}

function aStatError(code: string): NodeJS.ErrnoException {
  return Object.assign(new Error(`stat failed; code=${code}`) as NodeJS.ErrnoException, { code });
}

describe('TtlReconciliationService', () => {
  let service: TtlReconciliationService;
  let mockFileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;
  let mockBensyneClient: ReturnType<typeof aBensyneClientService>;
  let mockConfigurationService: ReturnType<typeof aConfigService>;
  let mockProcessingQueue: ReturnType<typeof aFileProcessingQueueService>;

  beforeEach(() => {
    mockFileMemoryTrackerService = aFileMemoryTrackerService();
    mockBensyneClient = aBensyneClientService();
    mockConfigurationService = aConfigService();
    mockProcessingQueue = aFileProcessingQueueService();
    fsMock.stat.mockReset();

    service = new TtlReconciliationService(
      mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
      mockBensyneClient as unknown as BensyneClient,
      mockConfigurationService as unknown as ConfigurationService,
      mockProcessingQueue as unknown as FileProcessingQueue,
      aLogger() as unknown as BasePinoLogger,
    );
  });

  describe('source selection', () => {
    it('never touches a source without ttlDays (findBySourceId/stat not called, no forgets)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([aSourceConfig({ id: 'src-no-ttl' })]);

      const summary = await service.run();

      expect(mockFileMemoryTrackerService.findBySourceId).not.toHaveBeenCalled();
      expect(fsMock.stat).not.toHaveBeenCalled();
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.sourcesChecked).toBe(0);
      expect(summary.expired).toBe(0);
      expect(summary.forgotten).toBe(0);
    });

    it('sweeps only sources with ttlDays when sourceId omitted (mix of with/without)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-no-ttl' }),
        aSourceConfig({ id: 'src-ttl', ttlDays: 365 }),
      ]);
      mockFileMemoryTrackerService.findBySourceId.mockImplementation(sourceId =>
        Promise.resolve(
          sourceId === 'src-ttl' ? [aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' })] : [],
        ),
      );
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 400 * MS_PER_DAY));

      jest.useFakeTimers();
      jest.setSystemTime(FIXED_NOW);
      const summary = await service.run();
      jest.useRealTimers();

      // No SQL cutoff: the sweep enumerates ALL rows of the source and derives expiry itself.
      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenCalledWith('src-ttl');
      expect(summary.sourcesChecked).toBe(1);
    });

    it('targets a single source when sourceId given', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-a', ttlDays: 100 }),
        aSourceConfig({ id: 'src-b', ttlDays: 200 }),
      ]);
      mockFileMemoryTrackerService.findBySourceId.mockImplementation(sourceId =>
        Promise.resolve(
          sourceId === 'src-b' ? [aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-b' })] : [],
        ),
      );
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 300 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 300 * MS_PER_DAY));

      jest.useFakeTimers();
      jest.setSystemTime(FIXED_NOW);
      await service.run(false, 'src-b');
      jest.useRealTimers();

      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenCalledWith('src-b');
    });
  });

  // ============================================================================
  // SUPERSEDES the old `cutoff computation` and `re-check before forget` pins of
  // this file (the `createdAt`-cutoff / `getTrackerCreatedAt` re-check assertions
  // at ~lines 60–200 of the pre-Task-3 version). Per spec §3.4 item 4 the pin
  // file the spec names (`src/application/services/ttl-clock-safety.spec.ts`) does
  // not exist at d2e3797 — verified drift, see parent-session
  // decomp-plan-rationale.md §1; the real old-contract pins were the ones here.
  // Rewritten to the activity contract per ADR-8 (clock = mtime, row.updatedAt ??
  // row.createdAt fallback only when the file is absent; strictly greater than
  // ttlDays = past due) as made the whole design by ADR-9 (gate-only).
  // Old→new coverage map (none silently deleted):
  // - "computes cutoff from ttlDays (before cutoff expired …)"      → 'forgets a present
  //   file with an old mtime …' + 'row old = now − ttlDays exactly … not past due' +
  //   'one millisecond past the boundary …' (strict-greater boundary now pinned directly).
  // - "does NOT forget a tracker whose createdAt is at/after cutoff" → 'does NOT forget …
  //   old createdAt but recent mtime' + 'absent file … recent row activity'.
  // - "re-reads the tracker and skips if no longer expired"          → the same two cases:
  //   with single-clock derivation such a row never enters the expired set. INTENTIONALLY
  //   REMOVED by ADR-9: the "initially SQL-expired → still counted in summary.expired"
  //   artifact of the double-clock design — summary.expired is exactly the activity-derived
  //   set now.
  // - "re-reads the tracker and skips if no longer exists"           → 'vanishes from the
  //   store mid-run (null row timestamps) is skipped, never forgotten' (liveness guard
  //   kept; the expired-count attribution above is intentionally removed).
  // - "recent updatedAt + old createdAt survives" (absent file): the rowUpdatedAt branch
  //   is not reachable through this service — the FileMemoryTracker aggregate is
  //   timestamp-free and the only in-scope row-activity channel is getTrackerCreatedAt
  //   (createdAt). updatedAt-beats-createdAt precedence stays pinned at the helper
  //   (ttl-activity.test.ts, Task 1); through here the row's observable activity is createdAt.
  // ============================================================================
  describe('activity-clock expiry derivation (B14b)', () => {
    const TRACKER = { id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 };

    beforeEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(FIXED_NOW);
      mockConfigurationService.getWatchSources.mockReturnValue([aSourceConfig(TRACKER)]);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 400 * MS_PER_DAY),
      );
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    const oneTrackedRow = (filePath: string) => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath, sourceId: TRACKER.id }),
      ]);
    };

    it('does NOT forget a tracked file with old createdAt but recent mtime (active file never prematurely forgotten)', async () => {
      oneTrackedRow('/repo/active.md');
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 700 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 1 * MS_PER_DAY));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.expired).toBe(0);
      expect(summary.forgotten).toBe(0);
    });

    it('forgets a present file with an old mtime and hard-deletes the row via the unchanged guard/forget path', async () => {
      oneTrackedRow('/repo/stale.md');
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 400 * MS_PER_DAY));

      const summary = await service.run();

      expect(fsMock.stat).toHaveBeenCalledWith('/repo/stale.md');
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/stale.md', 'bank-ttl');
      // Terminal operation unchanged (B1): bensyne forget success → deleteByFilePath.
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith('/repo/stale.md');
      expect(summary.expired).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('absent file (ENOENT) with recent row activity survives (row-metadata fallback clock)', async () => {
      oneTrackedRow('/repo/gone-recent.md');
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 1 * MS_PER_DAY),
      );
      fsMock.stat.mockRejectedValue(aStatError('ENOENT'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.expired).toBe(0);
      expect(summary.forgotten).toBe(0);
    });

    it('absent file (ENOENT) with old row activity is expired and forgotten (fallback clock clears the row)', async () => {
      oneTrackedRow('/repo/gone-stale.md');
      fsMock.stat.mockRejectedValue(aStatError('ENOENT'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/gone-stale.md', 'bank-ttl');
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith('/repo/gone-stale.md');
      expect(summary.expired).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('row last active exactly ttlDays ago (now − clock == ttlDays) is NOT past due (strict boundary)', async () => {
      oneTrackedRow('/repo/boundary-exact.md');
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 365 * MS_PER_DAY),
      );
      fsMock.stat.mockRejectedValue(aStatError('ENOENT'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.expired).toBe(0);
    });

    it('one millisecond past the boundary (now − clock > ttlDays) is past due and forgotten', async () => {
      oneTrackedRow('/repo/boundary-plus-1ms.md');
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 365 * MS_PER_DAY - 1),
      );
      fsMock.stat.mockRejectedValue(aStatError('ENOENT'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/boundary-plus-1ms.md', 'bank-ttl');
      expect(summary.expired).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('non-ENOENT stat error makes activity unobservable: the row is skipped, never forgotten', async () => {
      oneTrackedRow('/repo/unreadable.md');
      fsMock.stat.mockRejectedValue(aStatError('EACCES'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.expired).toBe(0);
      expect(summary.failed).toBe(0);
      expect(summary.forgotten).toBe(0);
    });

    it('a row that vanishes from the store mid-run (null row timestamps) is skipped, never forgotten', async () => {
      oneTrackedRow('/repo/vanished.md');
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(null);
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 400 * MS_PER_DAY));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
    });
  });

  describe('dry run', () => {
    it('run(dryRun=true): no forgetByFile calls, wouldForget counts expired, forgotten is 0', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' }),
        aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-ttl' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));

      const summary = await service.run(true);

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.wouldForget).toBe(2);
      expect(summary.forgotten).toBe(0);
      expect(summary.expired).toBe(2);
      expect(summary.dryRun).toBe(true);
    });
  });

  describe('real run', () => {
    it('forgets each expired tracker and deletes the tracker rows on success', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' }),
        aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-ttl' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(1, '/repo/a.md', 'bank-ttl');
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(2, '/repo/b.md', 'bank-ttl');
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(2);
      expect(summary.forgotten).toBe(2);
      expect(summary.failed).toBe(0);
      expect(summary.expired).toBe(2);
      expect(summary.dryRun).toBe(false);
    });

    it('does not call deleteByFilePath when forgetByFile returns ko (counted as failed, continues)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' }),
        aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-ttl' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      const summary = await service.run();

      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith('/repo/b.md');
      expect(summary.failed).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('deleteByFilePath throwing is counted as failed and does not throw', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' }),
        aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-ttl' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));
      mockFileMemoryTrackerService.deleteByFilePath.mockRejectedValueOnce(new Error('DB locked'));

      await expect(service.run()).resolves.not.toThrow();

      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(2);
    });

    it('forgetByFile returning ko continues processing remaining trackers (no throw)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' }),
        aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-ttl' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      await expect(service.run()).resolves.not.toThrow();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(1, '/repo/a.md', 'bank-ttl');
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(2, '/repo/b.md', 'bank-ttl');
    });
  });

  describe('mass-forget safeguard', () => {
    let savedForceForgetEnv: string | undefined;

    beforeEach(() => {
      savedForceForgetEnv = process.env.RACOCHU_RECONCILE_FORCE_FORGET;
    });

    afterEach(() => {
      if (savedForceForgetEnv === undefined) {
        delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      } else {
        process.env.RACOCHU_RECONCILE_FORCE_FORGET = savedForceForgetEnv;
      }
    });

    const createService = () =>
      new TtlReconciliationService(
        mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
        mockBensyneClient as unknown as BensyneClient,
        mockConfigurationService as unknown as ConfigurationService,
        mockProcessingQueue as unknown as FileProcessingQueue,
        aLogger() as unknown as BasePinoLogger,
      );

    it('REFUSES to mass-forget >20 expired for one source without force env (others still processed)', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const bigSource = aSourceConfig({ id: 'src-big', memoryBank: 'bank-big', ttlDays: 365 });
      const smallSource = aSourceConfig({ id: 'src-small', memoryBank: 'bank-small', ttlDays: 365 });
      mockConfigurationService.getWatchSources.mockReturnValue([bigSource, smallSource]);

      const bigTrackers = Array.from({ length: 21 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/big/file-${i}.md`, sourceId: 'src-big' }),
      );
      const smallTrackers = [aFileMemoryTracker({ filePath: '/repo/small/a.md', sourceId: 'src-small' })];

      mockFileMemoryTrackerService.findBySourceId.mockImplementation(sourceId => {
        if (sourceId === 'src-big') return Promise.resolve(bigTrackers);
        return Promise.resolve(smallTrackers);
      });
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));

      const summary = await testService.run();

      // No forgets for the big source
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalledWith(
        expect.stringContaining('/repo/big/'),
        'bank-big',
      );
      // Small source is still processed
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/small/a.md', 'bank-small');
      // Refusal is recorded; expired counts big+small
      expect(summary.refusedMassForget).toBe(1);
      expect(summary.expired).toBe(22);
      expect(summary.forgotten).toBe(1);
    });

    it('derives guard counts from the NEW activity set: 21 tracked but 10 expired is NOT refused', async () => {
      // The mass-forget threshold must compare the activity-derived expired set,
      // not the raw tracked-row count (B1: guard flow unchanged; B14b: input set changed).
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({ id: 'src-mixed', memoryBank: 'bank-mixed', ttlDays: 365 });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const rows = Array.from({ length: 21 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/mixed/file-${i}.md`, sourceId: 'src-mixed' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(rows);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockImplementation(async filePath => {
        const index = Number(String(filePath).match(/file-(\d+)\.md$/)?.[1] ?? -1);
        const ageMs = index < 10 ? 400 * MS_PER_DAY : 1 * MS_PER_DAY;
        return aFileStatWithMtimeMs(Date.now() - ageMs);
      });

      const summary = await testService.run();

      expect(summary.refusedMassForget).toBe(0);
      expect(summary.expired).toBe(10);
      expect(summary.forgotten).toBe(10);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(10);
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalledWith(
        expect.stringContaining('/repo/mixed/file-15.md'),
        'bank-mixed',
      );
    });

    it('OVERRIDE bypass: force-forget enabled → mass-forget proceeds', async () => {
      process.env.RACOCHU_RECONCILE_FORCE_FORGET = '1';
      const testService = createService();

      const source = aSourceConfig({ id: 'src-forced', memoryBank: 'bank-forced', ttlDays: 365 });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 25 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/forced/file-${i}.md`, sourceId: 'src-forced' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));

      const summary = await testService.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(25);
      expect(summary.forgotten).toBe(25);
      expect(summary.refusedMassForget).toBe(0);
    });
  });

  describe('config load failure', () => {
    it('returns an empty summary and does not throw', async () => {
      mockConfigurationService.getWatchSources.mockImplementation(() => {
        throw new Error('config missing');
      });

      await expect(service.run()).resolves.not.toThrow();

      const summary = await service.run().catch(() => {
        throw new Error('should not throw');
      });
      expect(summary.sourcesChecked).toBe(0);
      expect(summary.expired).toBe(0);
      expect(summary.forgotten).toBe(0);
      expect(mockFileMemoryTrackerService.findBySourceId).not.toHaveBeenCalled();
    });
  });

  describe('per-source error isolation', () => {
    it('continues processing remaining sources when findBySourceId fails for one', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-bad', memoryBank: 'bank-bad', ttlDays: 365 }),
        aSourceConfig({ id: 'src-good', memoryBank: 'bank-good', ttlDays: 365 }),
      ]);
      mockFileMemoryTrackerService.findBySourceId.mockImplementation(sourceId => {
        if (sourceId === 'src-bad') return Promise.reject(new Error('DB down'));
        return Promise.resolve([aFileMemoryTracker({ filePath: '/repo/good.md', sourceId: 'src-good' })]);
      });
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(Date.now() - 400 * MS_PER_DAY));

      await expect(service.run()).resolves.not.toThrow();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/good.md', 'bank-good');
    });
  });

  describe('startDailySweep / stop', () => {
    let intervalSpy: jest.SpyInstance;
    let clearSpy: jest.SpyInstance;

    beforeEach(() => {
      jest.useFakeTimers();
      intervalSpy = jest.spyOn(global, 'setInterval');
      clearSpy = jest.spyOn(global, 'clearInterval');
    });

    afterEach(() => {
      jest.useRealTimers();
      intervalSpy.mockRestore();
      clearSpy.mockRestore();
    });

    it('startDailySweep sets a daily interval and stop clears it', () => {
      service.startDailySweep();

      expect(intervalSpy).toHaveBeenCalledTimes(1);
      const [fn, delay] = intervalSpy.mock.calls[0];
      expect(delay).toBe(24 * 3600 * 1000);
      const intervalId = intervalSpy.mock.results[0].value;

      service.stop();

      expect(clearSpy).toHaveBeenCalledWith(intervalId);
    });

    it('onApplicationShutdown clears the interval', () => {
      service.startDailySweep();

      service.onApplicationShutdown();

      expect(clearSpy).toHaveBeenCalled();
    });

    it('the interval callback waits for the queue and runs the sweep', async () => {
      service.startDailySweep();

      // Advance 24h to fire the interval, then flush microtasks for the async callback.
      jest.advanceTimersByTime(24 * 3600 * 1000);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();

      expect(mockProcessingQueue.waitForEmpty).toHaveBeenCalled();
    });
  });

  // ============================================================================
  // Round-2 Task 6 — deleteDueFiles flag-gated delete tail (spec §3.2 chain,
  // §3.3 D2–D9, ADR-11). Flag-on fixtures declare an explicit resolvedPaths
  // root; `realpath` and `unlink` are explicit fs/promises mocks so call
  // PRESENCE and ORDER are assertable (the only new fs calls this feature adds).
  // All pre-existing suites above must pass UNMODIFIED (byte-kept invariants).
  // ============================================================================
  describe('deleteDueFiles flag-gated delete tail (round-2 §3.2, D2–D9)', () => {
    const DEL = { id: 'src-del', memoryBank: 'bank-del', ttlDays: 365, deleteDueFiles: true };
    const ROOT = '/roots/main';

    let savedForceForgetEnv: string | undefined;

    beforeEach(() => {
      savedForceForgetEnv = process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      jest.useFakeTimers();
      jest.setSystemTime(FIXED_NOW);
      fsMock.unlink.mockReset();
      fsMock.unlink.mockResolvedValue(undefined);
      fsMock.realpath.mockReset();
      setRealpathMap({});
      mockConfigurationService.getWatchSources.mockReturnValue([aSourceConfig({ ...DEL, path: ROOT })]);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(FIXED_NOW - 400 * MS_PER_DAY),
      );
      fsMock.stat.mockResolvedValue(aFileStatWithMtimeMs(FIXED_NOW - 400 * MS_PER_DAY));
    });

    afterEach(() => {
      jest.useRealTimers();
      if (savedForceForgetEnv === undefined) {
        delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      } else {
        process.env.RACOCHU_RECONCILE_FORCE_FORGET = savedForceForgetEnv;
      }
    });

    // fs.realpath stub: paths not in the map resolve to themselves (identity).
    function setRealpathMap(mapping: Record<string, string>): void {
      const impl = (candidate: string | { toString(): string }): Promise<string> => {
        const key = String(candidate);
        return Promise.resolve(mapping[key] ?? key);
      };
      fsMock.realpath.mockImplementation(impl as unknown as typeof fsPromises.realpath);
    }

    function anUnlinkError(code: 'ENOENT' | 'EPERM'): NodeJS.ErrnoException {
      return Object.assign(new Error(`unlink failed; code=${code}`), { code });
    }

    const createDeleteService = (): TtlReconciliationService =>
      new TtlReconciliationService(
        mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
        mockBensyneClient as unknown as BensyneClient,
        mockConfigurationService as unknown as ConfigurationService,
        mockProcessingQueue as unknown as FileProcessingQueue,
        aLogger() as unknown as BasePinoLogger,
      );

    const oneRow = (filePath: string): void => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath, sourceId: DEL.id }),
      ]);
    };

    const rowsUnderRoot = (count: number): void => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(
        Array.from({ length: count }, (_, i) =>
          aFileMemoryTracker({ filePath: `${ROOT}/file-${i}.md`, sourceId: DEL.id }),
        ),
      );
    };

    const countRealpathCallsFor = (target: string): number =>
      fsMock.realpath.mock.calls.filter((call: unknown[]) => call[0] === target).length;

    it('D2 flag-off: today\'s counters unchanged, all four new summary fields present at 0, unlink/realpath never called', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-off', memoryBank: 'bank-off', ttlDays: 365, path: ROOT }),
      ]);
      oneRow(`${ROOT}/stale.md`);

      const summary = await service.run();

      // Today's flag-off chain unchanged: forget + tracker-delete, forgotten=1.
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(`${ROOT}/stale.md`);
      expect(summary.forgotten).toBe(1);
      // New fields always present, initialized 0; no new statement executed.
      expect(summary.wouldDelete).toBe(0);
      expect(summary.deletedFiles).toBe(0);
      expect(summary.unlinkFailed).toBe(0);
      expect(summary.skippedConfinement).toBe(0);
      expect(fsMock.unlink).not.toHaveBeenCalled();
      expect(fsMock.realpath).not.toHaveBeenCalled();
    });

    it('D3 flag-on success chain: realpath precedes forget; unlink(file path) after tracker-delete; forgotten=1 deletedFiles=1', async () => {
      oneRow(`${ROOT}/a.md`);
      setRealpathMap({ [ROOT]: '/real/main', [`${ROOT}/a.md`]: '/real/main/a.md' });

      const summary = await service.run();

      expect(fsMock.realpath).toHaveBeenCalledWith(ROOT);
      expect(fsMock.realpath).toHaveBeenCalledWith(`${ROOT}/a.md`);
      // Chain step K precedes step D2: the first realpath call comes before the
      // first forget call.
      expect(fsMock.realpath.mock.invocationCallOrder[0]).toBeLessThan(
        mockBensyneClient.forgetByFile.mock.invocationCallOrder[0],
      );
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(`${ROOT}/a.md`);
      // Unlink targets the tracked file path, not the realpath output.
      expect(fsMock.unlink).toHaveBeenCalledTimes(1);
      expect(fsMock.unlink).toHaveBeenCalledWith(`${ROOT}/a.md`);
      expect(summary.forgotten).toBe(1);
      expect(summary.deletedFiles).toBe(1);
      expect(summary.wouldDelete).toBe(0);
      expect(summary.unlinkFailed).toBe(0);
      expect(summary.skippedConfinement).toBe(0);
      expect(summary.failed).toBe(0);
    });

    it('D3 flag-on: declared roots are realpath-resolved once per source (two contained files → one root realpath)', async () => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: `${ROOT}/a.md`, sourceId: DEL.id }),
        aFileMemoryTracker({ filePath: `${ROOT}/b.md`, sourceId: DEL.id }),
      ]);

      const summary = await service.run();

      expect(countRealpathCallsFor(ROOT)).toBe(1);
      expect(fsMock.unlink).toHaveBeenCalledTimes(2);
      expect(summary.forgotten).toBe(2);
      expect(summary.deletedFiles).toBe(2);
    });

    it('D4 flag-on dry-run: contained candidate counts wouldForget AND wouldDelete, touches nothing', async () => {
      oneRow(`${ROOT}/a.md`);

      const summary = await service.run(true);

      expect(summary.expired).toBe(1);
      expect(summary.wouldForget).toBe(1);
      expect(summary.wouldDelete).toBe(1);
      expect(summary.forgotten).toBe(0);
      expect(summary.deletedFiles).toBe(0);
      expect(summary.dryRun).toBe(true);
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(fsMock.unlink).not.toHaveBeenCalled();
    });

    it('D4+D9 flag-on dry-run: non-contained candidate → skippedConfinement=1, still zero other counters', async () => {
      oneRow(`${ROOT}/escape.md`);
      setRealpathMap({ [`${ROOT}/escape.md`]: '/outside/real.md' });

      const summary = await service.run(true);

      expect(summary.expired).toBe(1);
      expect(summary.skippedConfinement).toBe(1);
      expect(summary.wouldForget).toBe(0);
      expect(summary.wouldDelete).toBe(0);
      expect(summary.forgotten).toBe(0);
      expect(summary.deletedFiles).toBe(0);
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(fsMock.unlink).not.toHaveBeenCalled();
    });

    it('D9 confinement precedes every side effect: escaping symlink skipped whole (realpath before any call); in-root file in same run fully processed; root resolved once', async () => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: `${ROOT}/link-out.md`, sourceId: DEL.id }),
        aFileMemoryTracker({ filePath: `${ROOT}/in-root.md`, sourceId: DEL.id }),
      ]);
      setRealpathMap({ [`${ROOT}/link-out.md`]: '/elsewhere/target.md' });

      const summary = await service.run();

      expect(summary.skippedConfinement).toBe(1);
      // The escaped file produced ZERO side effects: forget/tracker/unlink ran
      // once each, and only for the in-root file.
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(`${ROOT}/in-root.md`, 'bank-del');
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(`${ROOT}/in-root.md`);
      expect(fsMock.unlink).toHaveBeenCalledTimes(1);
      expect(fsMock.unlink).toHaveBeenCalledWith(`${ROOT}/in-root.md`);
      // Call ORDER: the escaped file's confinement check precedes the first
      // forget call of the run.
      const escapeCheckIndex = fsMock.realpath.mock.calls.findIndex(
        (call: unknown[]) => call[0] === `${ROOT}/link-out.md`,
      );
      expect(escapeCheckIndex).toBeGreaterThanOrEqual(0);
      expect(fsMock.realpath.mock.invocationCallOrder[escapeCheckIndex]).toBeLessThan(
        mockBensyneClient.forgetByFile.mock.invocationCallOrder[0],
      );
      // Roots realpath-resolved ONCE per source despite two candidates.
      expect(countRealpathCallsFor(ROOT)).toBe(1);
      expect(summary.forgotten).toBe(1);
      expect(summary.deletedFiles).toBe(1);
      expect(summary.failed).toBe(0);
    });

    it('D9: the declared root itself is never a delete target (realpath equals the root → skipped)', async () => {
      oneRow(ROOT);

      const summary = await service.run();

      expect(summary.skippedConfinement).toBe(1);
      expect(fsMock.unlink).not.toHaveBeenCalled();
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.deletedFiles).toBe(0);
    });

    it('D5 flag-on forget ko: failed=1, never unlinks, deletedFiles stays 0, never throws', async () => {
      oneRow(`${ROOT}/a.md`);
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      const runPromise = service.run();
      await expect(runPromise).resolves.not.toThrow();
      const summary = await runPromise;

      expect(summary.failed).toBe(1);
      expect(summary.forgotten).toBe(0);
      expect(summary.deletedFiles).toBe(0);
      expect(summary.unlinkFailed).toBe(0);
      expect(fsMock.unlink).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
    });

    it('D6 flag-on tracker-delete throw: no unlink; second sweep over the same state converges (forget no-op, row goes, unlink then) — zero new state', async () => {
      oneRow(`${ROOT}/a.md`);
      mockFileMemoryTrackerService.deleteByFilePath.mockRejectedValueOnce(new Error('DB locked'));

      const first = await service.run();
      expect(first.failed).toBe(1);
      expect(first.deletedFiles).toBe(0);
      expect(first.forgotten).toBe(0);
      expect(fsMock.unlink).not.toHaveBeenCalled();

      // Same run state (row still present; forgetByFile remains an idempotent
      // ok no-op per MEM-0026). A plain second run() — no new state anywhere.
      const second = await service.run();
      expect(second.failed).toBe(0);
      expect(second.forgotten).toBe(1);
      expect(second.deletedFiles).toBe(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(2);
      expect(fsMock.unlink).toHaveBeenCalledTimes(1);
      expect(fsMock.unlink).toHaveBeenCalledWith(`${ROOT}/a.md`);
    });

    it('D7 flag-on unlink ENOENT: reached-goal — deletedFiles++ and forgotten++ (mermaid N), not unlinkFailed, never throws', async () => {
      oneRow(`${ROOT}/gone.md`);
      fsMock.unlink.mockRejectedValueOnce(anUnlinkError('ENOENT'));

      const runPromise = service.run();
      await expect(runPromise).resolves.not.toThrow();
      const summary = await runPromise;

      expect(summary.deletedFiles).toBe(1);
      expect(summary.forgotten).toBe(1);
      expect(summary.unlinkFailed).toBe(0);
      expect(summary.failed).toBe(0);
    });

    it('D8 flag-on unlink EPERM: unlinkFailed=1 non-fatal, remaining files unaffected, never throws', async () => {
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: `${ROOT}/locked.md`, sourceId: DEL.id }),
        aFileMemoryTracker({ filePath: `${ROOT}/ok.md`, sourceId: DEL.id }),
      ]);
      fsMock.unlink.mockRejectedValueOnce(anUnlinkError('EPERM'));

      const runPromise = service.run();
      await expect(runPromise).resolves.not.toThrow();
      const summary = await runPromise;

      expect(summary.unlinkFailed).toBe(1);
      // The EPERM file is the ONLY shortfall: the second file completed fully.
      expect(summary.deletedFiles).toBe(1);
      expect(summary.forgotten).toBe(1);
      expect(summary.failed).toBe(0);
      expect(fsMock.unlink).toHaveBeenCalledTimes(2);
    });

    it('mass-cap by construction: flag-on over threshold is REFUSED, unlink never called, deletedFiles=0', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createDeleteService();
      rowsUnderRoot(21);

      const summary = await testService.run();

      expect(summary.refusedMassForget).toBe(1);
      expect(summary.expired).toBe(21);
      expect(summary.forgotten).toBe(0);
      expect(summary.deletedFiles).toBe(0);
      expect(summary.skippedConfinement).toBe(0);
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(fsMock.unlink).not.toHaveBeenCalled();
    });

    it('mass-cap by construction: RACOCHU_RECONCILE_FORCE_FORGET=1 → the batch forgets AND unlinks (bounded together)', async () => {
      process.env.RACOCHU_RECONCILE_FORCE_FORGET = '1';
      const testService = createDeleteService();
      rowsUnderRoot(21);

      const summary = await testService.run();

      expect(summary.refusedMassForget).toBe(0);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(21);
      expect(fsMock.unlink).toHaveBeenCalledTimes(21);
      expect(summary.forgotten).toBe(21);
      expect(summary.deletedFiles).toBe(21);
    });
  });
});
