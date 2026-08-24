import fs from 'fs';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { aSourceConfig } from '../infrastructure/config/configuration.service.test-utils';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { aFileMemoryTracker } from '../infrastructure/repositories/file-memory-tracker.repository.test-utils';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';
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
});
