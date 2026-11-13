import fs from 'fs';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { aSourceConfig } from '../../infrastructure/config/configuration.service.test-utils';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { aFileMemoryTracker } from '../../infrastructure/repositories/file-memory-tracker.repository.test-utils';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { MASS_FORGET_THRESHOLD } from '../mass-forget-guard';
import { ExcludeReconciliationService } from './exclude-reconciliation.service';

describe('ExcludeReconciliationService', () => {
  let service: ExcludeReconciliationService;
  let mockFileMemoryTrackerService: jest.Mocked<{
    findBySourceId: jest.Mock;
    deleteByFilePath: jest.Mock;
  }>;
  let mockBensyneClient: jest.Mocked<{ forgetByFile: jest.Mock }>;
  let mockConfigurationService: jest.Mocked<{ getWatchSources: jest.Mock }>;
  let existsSyncSpy: jest.SpyInstance<boolean, [path: fs.PathLike]>;

  beforeEach(() => {
    mockFileMemoryTrackerService = {
      findBySourceId: jest.fn().mockResolvedValue([]),
      deleteByFilePath: jest.fn().mockResolvedValue(undefined),
    };
    mockBensyneClient = {
      forgetByFile: jest.fn().mockResolvedValue(Result.ok({ status: 'forgotten' })),
    };
    mockConfigurationService = {
      getWatchSources: jest.fn().mockReturnValue([]),
    };
    existsSyncSpy = jest.spyOn(fs, 'existsSync').mockReturnValue(true);

    service = new ExcludeReconciliationService(
      mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
      mockBensyneClient as unknown as BensyneClient,
      mockConfigurationService as unknown as ConfigurationService,
      aLogger() as unknown as BasePinoLogger,
    );
  });

  afterEach(() => {
    existsSyncSpy.mockRestore();
  });

  describe('per-source tracker lookup', () => {
    it('calls findBySourceId for every watch source', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-1' }),
        aSourceConfig({ id: 'src-2' }),
      ]);

      await service.run();

      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenNthCalledWith(1, 'src-1');
      expect(mockFileMemoryTrackerService.findBySourceId).toHaveBeenNthCalledWith(2, 'src-2');
    });

    it('continues reconciling remaining sources when findBySourceId fails for one', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([
        aSourceConfig({ id: 'src-bad', exclude: ['**/tool-responses/**'] }),
        aSourceConfig({ id: 'src-good', exclude: ['**/tool-responses/**'] }),
      ]);
      mockFileMemoryTrackerService.findBySourceId.mockImplementation((sourceId: string) => {
        if (sourceId === 'src-bad') {
          return Promise.reject(new Error('DB down'));
        }
        return Promise.resolve([
          aFileMemoryTracker({ filePath: '/repo/tool-responses/late.log', sourceId: 'src-good' }),
        ]);
      });

      await expect(service.run()).resolves.not.toThrow();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(
        '/repo/tool-responses/late.log',
        aSourceConfig({ id: 'src-good' }).memoryBank,
      );
    });
  });

  describe('forget decisions', () => {
    const excludedSource = aSourceConfig({
      id: 'src-1',
      memoryBank: 'bank-1',
      exclude: ['**/tool-responses/**'],
    });

    it('forgets a tracked excluded file that still exists on disk', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/x.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      await service.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/tool-responses/x.log', 'bank-1');
    });

    it('does not forget a tracked excluded file that no longer exists on disk', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/gone.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(false);

      await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
    });

    it('does not forget tracked files that do not match any exclude pattern', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
    });

    it('does not forget any files when a source has no exclude patterns', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([aSourceConfig({ id: 'src-1' })]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-1' }),
      ]);

      await service.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
    });

    it('still checks disk existence only for excluded files (non-excluded skipped before fs access)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      await service.run();

      expect(existsSyncSpy).not.toHaveBeenCalled();
    });
  });

  describe('tracker cleanup', () => {
    const excludedSource = aSourceConfig({
      id: 'src-1',
      memoryBank: 'bank-1',
      exclude: ['**/tool-responses/**'],
    });

    it('calls deleteByFilePath for each excluded file when forgetByFile returns ok', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-1' }),
        aFileMemoryTracker({ filePath: '/repo/tool-responses/b.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      await service.run();

      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenNthCalledWith(
        1,
        '/repo/tool-responses/a.log',
      );
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenNthCalledWith(
        2,
        '/repo/tool-responses/b.log',
      );
    });

    it('does NOT call deleteByFilePath when forgetByFile returns ko (counted as failed, continues)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-1' }),
        aFileMemoryTracker({ filePath: '/repo/tool-responses/b.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      const summary = await service.run();

      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(
        '/repo/tool-responses/b.log',
      );
      expect(summary.failed).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('when deleteByFilePath throws, reconciliation counts failed, logs warn, and continues (never throws)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-1' }),
        aFileMemoryTracker({ filePath: '/repo/tool-responses/b.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);
      mockFileMemoryTrackerService.deleteByFilePath.mockRejectedValueOnce(new Error('DB locked'));

      const summary = await service.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(2);
      expect(summary.failed).toBe(1);
      expect(summary.forgotten).toBe(1);
    });

    it('non-excluded files never trigger deleteByFilePath', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      await service.run();

      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
    });
  });

  describe('failure isolation', () => {
    const excludedSource = aSourceConfig({
      id: 'src-1',
      memoryBank: 'bank-1',
      exclude: ['**/tool-responses/**'],
    });

    it('continues processing remaining files when a single forgetByFile returns ko', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-1' }),
        aFileMemoryTracker({ filePath: '/repo/tool-responses/b.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValue(true);
      mockBensyneClient.forgetByFile.mockResolvedValueOnce(
        Result.ko([new ErrorWithDetails('FORGET_FAILED', 'Bensyne unreachable')]),
      );

      await expect(service.run()).resolves.not.toThrow();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(
        1,
        '/repo/tool-responses/a.log',
        'bank-1',
      );
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(
        2,
        '/repo/tool-responses/b.log',
        'bank-1',
      );
    });
  });

  describe('idempotency', () => {
    const excludedSource = aSourceConfig({
      id: 'src-1',
      memoryBank: 'bank-1',
      exclude: ['**/tool-responses/**'],
    });

    it('running twice is safe (second run no-ops already-gone files, re-calls ok for existing ones)', async () => {
      mockConfigurationService.getWatchSources.mockReturnValue([excludedSource]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/x.log', sourceId: 'src-1' }),
      ]);
      existsSyncSpy.mockReturnValueOnce(true).mockReturnValueOnce(false);

      await service.run();
      await service.run();

      // Only the first run (file on disk) triggered a forget; second run skipped.
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
    });
  });

  describe('mass-forget safeguard', () => {
    let savedForceForgetEnv: string | undefined;

    beforeEach(() => {
      savedForceForgetEnv = process.env.RACOCHU_RECONCILE_FORCE_FORGET;
    });

    afterEach(() => {
      // Restore original env
      if (savedForceForgetEnv === undefined) {
        delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      } else {
        process.env.RACOCHU_RECONCILE_FORCE_FORGET = savedForceForgetEnv;
      }
    });

    // Helper to create service (re-reads env vars)
    const createService = () =>
      new ExcludeReconciliationService(
        mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
        mockBensyneClient as unknown as BensyneClient,
        mockConfigurationService as unknown as ConfigurationService,
        aLogger() as unknown as BasePinoLogger,
      );

    it('REFUSES to mass-forget: source with 100 tracked files, excludes match all 100 → no forgets, refusedMassForget=1', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-mass',
        memoryBank: 'bank-mass',
        exclude: ['**/.*/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 100 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/.hidden/file-${i}.md`, sourceId: 'src-mass' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      // No files should be forgotten
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.failed).toBe(0);
      // Refusal should be recorded
      expect(summary.refusedMassForget).toBe(1);
    });

    it('REFUSES when excludes match more than threshold (50 > 20)', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-many',
        memoryBank: 'bank-many',
        exclude: ['**/excluded/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 50 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/excluded/file-${i}.log`, sourceId: 'src-many' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.refusedMassForget).toBe(1);
    });

    it('PRESERVES normal small-forget: 5 tracked files, 2 match excludes (under threshold)', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-small',
        memoryBank: 'bank-small',
        exclude: ['**/tool-responses/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = [
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-small' }),
        aFileMemoryTracker({ filePath: '/repo/tool-responses/b.log', sourceId: 'src-small' }),
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-small' }),
        aFileMemoryTracker({ filePath: '/repo/notes/y.md', sourceId: 'src-small' }),
        aFileMemoryTracker({ filePath: '/repo/notes/z.md', sourceId: 'src-small' }),
      ];
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      // Should forget the 2 excluded files
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(
        1,
        '/repo/tool-responses/a.log',
        'bank-small',
      );
      expect(mockBensyneClient.forgetByFile).toHaveBeenNthCalledWith(
        2,
        '/repo/tool-responses/b.log',
        'bank-small',
      );
      expect(summary.forgotten).toBe(2);
      expect(summary.refusedMassForget).toBe(0);
    });

    it('OVERRIDE bypass: force-forget enabled → mass-forget proceeds despite exceeding threshold', async () => {
      process.env.RACOCHU_RECONCILE_FORCE_FORGET = '1';
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-forced',
        memoryBank: 'bank-forced',
        exclude: ['**/.*/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 50 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/.hidden/file-${i}.md`, sourceId: 'src-forced' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      // All files should be forgotten
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(50);
      expect(summary.forgotten).toBe(50);
      expect(summary.refusedMassForget).toBe(0);
    });

    it('NEVER throws on guard path (non-fatal)', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-guard',
        memoryBank: 'bank-guard',
        exclude: ['**/.*/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);

      const trackers = Array.from({ length: 100 }, (_, i) =>
        aFileMemoryTracker({ filePath: `/repo/.hidden/file-${i}.md`, sourceId: 'src-guard' }),
      );
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(trackers);
      existsSyncSpy.mockReturnValue(true);

      // Should not throw
      await expect(testService.run()).resolves.not.toThrow();
    });
  });

  describe('include narrowing — out-of-scope selection (EP4, spec §5 / ADR-6)', () => {
    // Generalized semantics: a tracked file is a forget-candidate iff it is
    // OUT OF SCOPE — matched by no include pattern when one is present, or
    // matched by an exclude pattern (same shared scope composition as the
    // other EPs). Mass-forget guard, threshold, FORCE_FORGET env handling,
    // existsSync skip and tracker cleanup are unchanged by design — only the
    // candidate SET generalizes.
    const aboveThresholdCount = MASS_FORGET_THRESHOLD + 30;

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

    // Guard tests construct their own service (the constructor re-reads env).
    const createService = () =>
      new ExcludeReconciliationService(
        mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
        mockBensyneClient as unknown as BensyneClient,
        mockConfigurationService as unknown as ConfigurationService,
        aLogger() as unknown as BasePinoLogger,
      );

    it('include-present: non-matching tracked files are forgotten; matching ones are NEVER touched', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-inc',
        memoryBank: 'bank-inc',
        exclude: [],
        include: ['**/*.md'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-inc' }),
        aFileMemoryTracker({ filePath: '/repo/data/y.txt', sourceId: 'src-inc' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      // ONLY the include-non-matching file is a candidate and gets forgotten.
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/data/y.txt', 'bank-inc');
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith('/repo/data/y.txt');
      expect(summary.forgotten).toBe(1);
      // A matching (in-scope) file is skipped ENTIRELY — not even disk-checked.
      expect(existsSyncSpy).not.toHaveBeenCalledWith('/repo/notes/x.md');
    });

    it('include-absent: selection is IDENTICAL to the exclude-only semantics (no adaptation)', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-abs',
        memoryBank: 'bank-abs',
        exclude: ['**/tool-responses/**'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/tool-responses/a.log', sourceId: 'src-abs' }),
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-abs' }),
      ]);
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith('/repo/tool-responses/a.log', 'bank-abs');
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(
        '/repo/tool-responses/a.log',
      );
      expect(existsSyncSpy).not.toHaveBeenCalledWith('/repo/notes/x.md');
      expect(summary.forgotten).toBe(1);
      expect(summary.refusedMassForget).toBe(0);
    });

    it('include-narrowed candidates above the threshold → REFUSED: nothing forgotten, refusedMassForget=1', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      // No exclude matches anything here — the candidate set exists ONLY
      // because the include rollout pushed tracked files out of scope
      // (ADR-6: the guard covers include rollouts for free).
      const source = aSourceConfig({
        id: 'src-rollout',
        memoryBank: 'bank-rollout',
        exclude: [],
        include: ['**/*.md'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(
        Array.from({ length: aboveThresholdCount }, (_, i) =>
          aFileMemoryTracker({ filePath: `/repo/data/file-${i}.txt`, sourceId: 'src-rollout' }),
        ),
      );
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.forgotten).toBe(0);
      expect(summary.refusedMassForget).toBe(1);
    });

    it('RACOCHU_RECONCILE_FORCE_FORGET=1 proceeds with the include-narrowed set', async () => {
      process.env.RACOCHU_RECONCILE_FORCE_FORGET = '1';
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-forced-inc',
        memoryBank: 'bank-forced-inc',
        exclude: [],
        include: ['**/*.md'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue(
        Array.from({ length: aboveThresholdCount }, (_, i) =>
          aFileMemoryTracker({ filePath: `/repo/data/file-${i}.txt`, sourceId: 'src-forced-inc' }),
        ),
      );
      existsSyncSpy.mockReturnValue(true);

      const summary = await testService.run();

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(aboveThresholdCount);
      expect(summary.forgotten).toBe(aboveThresholdCount);
      expect(summary.refusedMassForget).toBe(0);
    });

    it('include-narrowed candidate missing on disk is still skipped; in-scope files never disk-checked', async () => {
      delete process.env.RACOCHU_RECONCILE_FORCE_FORGET;
      const testService = createService();

      const source = aSourceConfig({
        id: 'src-gone',
        memoryBank: 'bank-gone',
        exclude: [],
        include: ['**/*.md'],
      });
      mockConfigurationService.getWatchSources.mockReturnValue([source]);
      mockFileMemoryTrackerService.findBySourceId.mockResolvedValue([
        aFileMemoryTracker({ filePath: '/repo/notes/x.md', sourceId: 'src-gone' }),
        aFileMemoryTracker({ filePath: '/repo/data/gone.txt', sourceId: 'src-gone' }),
      ]);
      existsSyncSpy.mockImplementation(p => p !== '/repo/data/gone.txt');

      const summary = await testService.run();

      // Out-of-scope but absent → counted as skipped, NOT forgotten/failed;
      // the tracker row must be left alone (existsSync skip path unchanged).
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
      expect(summary.skipped).toBe(1);
      expect(summary.forgotten).toBe(0);
      expect(summary.failed).toBe(0);
      expect(existsSyncSpy).not.toHaveBeenCalledWith('/repo/notes/x.md');
    });
  });
});
