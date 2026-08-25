import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { aConfigService, aSourceConfig } from '../infrastructure/config/configuration.service.test-utils';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { aFileMemoryTracker } from '../infrastructure/repositories/file-memory-tracker.repository.test-utils';
import { aBensyneClientService } from '../infrastructure/services/bensyne-client.test-utils';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { aFileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service.test-utils';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { aFileProcessingQueueService } from '../infrastructure/services/file-processing-queue.test-utils';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';
import { TtlReconciliationService } from './ttl-reconciliation.service';

const MS_PER_DAY = 86_400_000;

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

    service = new TtlReconciliationService(
      mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
      mockBensyneClient as unknown as BensyneClient,
      mockConfigurationService as unknown as ConfigurationService,
      mockProcessingQueue as unknown as FileProcessingQueue,
      aLogger() as unknown as BasePinoLogger,
    );
  });

  describe('source selection', () => {
    it('never touches a source without ttlDays (findExpiredBySourceId not called, no forgets)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([aSourceConfig({ id: 'src-no-ttl' })]);

      const summary = await service.run();

      expect(mockFileMemoryTrackerService.findExpiredBySourceId).not.toHaveBeenCalled();
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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockImplementation(sourceId =>
        Promise.resolve(
          sourceId === 'src-ttl' ? [aFileMemoryTracker({ filePath: '/repo/a.md', sourceId: 'src-ttl' })] : [],
        ),
      );
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

      const summary = await service.run();

      expect(mockFileMemoryTrackerService.findExpiredBySourceId).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.findExpiredBySourceId).toHaveBeenCalledWith(
        'src-ttl',
        expect.any(Date),
      );
      expect(summary.sourcesChecked).toBe(1);
    });

    it('targets a single source when sourceId given', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-a', ttlDays: 100 }),
        aSourceConfig({ id: 'src-b', ttlDays: 200 }),
      ]);
      mockFileMemoryTrackerService.findExpiredBySourceId.mockImplementation(sourceId =>
        Promise.resolve(
          sourceId === 'src-b' ? [aFileMemoryTracker({ filePath: '/repo/b.md', sourceId: 'src-b' })] : [],
        ),
      );
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 300 * MS_PER_DAY),
      );

      await service.run(false, 'src-b');

      expect(mockFileMemoryTrackerService.findExpiredBySourceId).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.findExpiredBySourceId).toHaveBeenCalledWith(
        'src-b',
        expect.any(Date),
      );
    });
  });

  describe('cutoff computation', () => {
    it('computes cutoff from ttlDays (before cutoff expired, after cutoff not)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      // One tracker returned by the repo (mocked as expired); we verify the cutoff
      // passed to findExpiredBySourceId is ~now - 365 days.
      const oldTracker = aFileMemoryTracker({ filePath: '/repo/old.md', sourceId: 'src-ttl' });
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue([oldTracker]);
      const beforeCall = Date.now();
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockImplementation(filePath => {
        // Return a createdAt strictly before the cutoff so it is forgotten.
        return Promise.resolve(new Date(beforeCall - 400 * MS_PER_DAY));
      });

      await service.run();

      expect(mockFileMemoryTrackerService.findExpiredBySourceId).toHaveBeenCalledTimes(1);
      const cutoffArg = mockFileMemoryTrackerService.findExpiredBySourceId.mock.calls[0][1] as Date;
      const expectedApprox = beforeCall - 365 * MS_PER_DAY;
      // Allow tolerance for a few ms.
      expect(Math.abs(cutoffArg.getTime() - expectedApprox)).toBeLessThan(1000);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/old.md', 'bank-ttl');
    });

    it('does NOT forget a tracker whose createdAt is at/after the cutoff (re-check skips it)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const freshTracker = aFileMemoryTracker({ filePath: '/repo/fresh.md', sourceId: 'src-ttl' });
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue([freshTracker]);
      // Re-check: createdAt is recent (not expired).
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(new Date(Date.now()));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.failed).toBe(0);
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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
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
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      await expect(service.run()).resolves.not.toThrow();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(1, '/repo/a.md', 'bank-ttl');
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(2, '/repo/b.md', 'bank-ttl');
    });
  });

  describe('re-check before forget', () => {
    it('re-reads the tracker and skips if no longer expired (createdAt at/after cutoff)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const tracker = aFileMemoryTracker({ filePath: '/repo/x.md', sourceId: 'src-ttl' });
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue([tracker]);
      // Re-check returns a fresh createdAt -> no longer expired.
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(new Date(Date.now()));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      // The tracker was initially expired, so it's counted in expired.
      expect(summary.expired).toBe(1);
    });

    it('re-reads the tracker and skips if no longer exists (null createdAt)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-ttl', memoryBank: 'bank-ttl', ttlDays: 365 }),
      ]);
      const tracker = aFileMemoryTracker({ filePath: '/repo/y.md', sourceId: 'src-ttl' });
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue([tracker]);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(null);

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.expired).toBe(1);
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

      mockFileMemoryTrackerService.findExpiredBySourceId.mockImplementation(sourceId => {
        if (sourceId === 'src-big') return Promise.resolve(bigTrackers);
        return Promise.resolve(smallTrackers);
      });
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

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

    it('OVERRIDE bypass: force-forget enabled → mass-forget proceeds', async () => {
      process.env.RACOCHU_RECONCILE_FORCE_FORGET = '1';
      const testService = createService();

      const source = aSourceConfig({ id: 'src-forced', memoryBank: 'bank-forced', ttlDays: 365 });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 25 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/forced/file-${i}.md`, sourceId: 'src-forced' }),
      );
      mockFileMemoryTrackerService.findExpiredBySourceId.mockResolvedValue(trackers);
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

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
      expect(mockFileMemoryTrackerService.findExpiredBySourceId).not.toHaveBeenCalled();
    });
  });

  describe('per-source error isolation', () => {
    it('continues processing remaining sources when findExpiredBySourceId fails for one', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-bad', memoryBank: 'bank-bad', ttlDays: 365 }),
        aSourceConfig({ id: 'src-good', memoryBank: 'bank-good', ttlDays: 365 }),
      ]);
      mockFileMemoryTrackerService.findExpiredBySourceId.mockImplementation(sourceId => {
        if (sourceId === 'src-bad') return Promise.reject(new Error('DB down'));
        return Promise.resolve([aFileMemoryTracker({ filePath: '/repo/good.md', sourceId: 'src-good' })]);
      });
      mockFileMemoryTrackerService.getTrackerCreatedAt.mockResolvedValue(
        new Date(Date.now() - 400 * MS_PER_DAY),
      );

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
});
