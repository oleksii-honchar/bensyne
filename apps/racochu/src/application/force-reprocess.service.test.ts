import '@/utils/mastra-rag.test-utils';

import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import * as path from 'path';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { aFileProcessingQueueService } from '../infrastructure/services/file-processing-queue.test-utils';
import { ProcessFileUseCase } from '../use-cases/process-file.use-case';
import { aProcessFileUseCase } from '../use-cases/process-file.use-case.test-utils';
import { Result } from '../utils/result';
import { mockDirStats, mockDirent, mockFileStats } from '../utils/test-utils';
import { ForceReprocessService } from './force-reprocess.service';

jest.mock('fs/promises');
const fsMock = fsPromises as jest.Mocked<typeof fsPromises>;

describe('ForceReprocessService', () => {
  let service: ForceReprocessService;
  let processFileUseCase: ReturnType<typeof aProcessFileUseCase>;
  let processingQueue: ReturnType<typeof aFileProcessingQueueService>;
  let logger: ReturnType<typeof aLogger>;

  beforeEach(async () => {
    jest.clearAllMocks();
    fsMock.stat.mockReset();
    fsMock.readdir.mockReset();

    processFileUseCase = aProcessFileUseCase();
    processingQueue = aFileProcessingQueueService();
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ForceReprocessService,
        { provide: ProcessFileUseCase, useValue: processFileUseCase },
        { provide: FileProcessingQueue, useValue: processingQueue },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    service = module.get<ForceReprocessService>(ForceReprocessService);
  });

  describe('forceReprocessAll', () => {
    it('should process files from all sources', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1' }), aWatchSourceConfig({ id: 'source-2' })];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      await service.forceReprocessAll(sources);

      // 2 sources × 1 file each = 2 queue entries
      expect(processingQueue.addToQueue).toHaveBeenCalledTimes(2);
    });

    it('should queue files found in each source', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' })];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

      await service.forceReprocessAll(sources);

      expect(processingQueue.addToQueue).toHaveBeenCalledTimes(2);
    });
  });

  describe('forceReprocessSource', () => {
    it('should process files from specific source by id', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      await service.forceReprocessSource('source-1', sources);

      expect(processingQueue.addToQueue).toHaveBeenCalledTimes(1);
    });

    it('should skip when source not found', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1' })];

      await service.forceReprocessSource('non-existent', sources);

      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });
  });

  describe('directory scanning', () => {
    it('should scan directory recursively', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('file1.md', false), mockDirent('subdir', true)])
        .mockResolvedValueOnce([mockDirent('file2.md', false)]);

      await service.forceReprocessAll([source]);

      expect(fsMock.readdir).toHaveBeenCalledTimes(2);
      expect(fsMock.readdir).toHaveBeenCalledWith('/tmp/test', { withFileTypes: true });
      expect(fsMock.readdir).toHaveBeenCalledWith('/tmp/test/subdir', { withFileTypes: true });
    });

    it('should not queue files when path is not a directory', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockFileStats());

      await service.forceReprocessAll([source]);

      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should not queue files when stat fails', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockRejectedValue(new Error('ENOENT'));

      await service.forceReprocessAll([source]);

      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });
  });

  describe('queue population', () => {
    it('should add each file to processing queue', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

      await service.forceReprocessAll([source]);

      expect(processingQueue.addToQueue).toHaveBeenCalledTimes(2);
    });

    it('should call processFileUseCase for each queued file', async () => {
      const source = aWatchSourceConfig({ id: 'my-source', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      processFileUseCase.execute.mockResolvedValue(Result.ok(undefined as unknown as void));

      await service.forceReprocessAll([source]);

      // Extract the task function and execute it
      const task = processingQueue.addToQueue.mock.calls[0][0] as () => Promise<void>;
      await task();

      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/file1.md',
        eventType: 'add',
        sourceId: 'my-source',
        memoryBank: 'my-source',
        sourceConfig: source,
      });
    });

    it('should handle file reprocessing failure gracefully', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      processFileUseCase.execute.mockResolvedValue(Result.ko([new Error('Processing failed')]));

      await service.forceReprocessAll([source]);

      const task = processingQueue.addToQueue.mock.calls[0][0] as () => Promise<void>;
      // Task should not throw — it swallows errors via logging
      await expect(task()).resolves.not.toThrow();
    });
  });

  describe('path resolution', () => {
    it('should resolve tilde paths to home directory', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '~/documents' });

      fsMock.stat.mockResolvedValue(mockFileStats());

      await service.forceReprocessAll([source]);

      expect(fsMock.stat).toHaveBeenCalledWith(
        expect.stringContaining(path.join(process.env.HOME || '/home/user', 'documents')),
      );
    });

    it('should resolve relative paths', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: './relative' });

      fsMock.stat.mockResolvedValue(mockFileStats());

      await service.forceReprocessAll([source]);

      expect(fsMock.stat).toHaveBeenCalledWith(expect.stringContaining(path.resolve('./relative')));
    });
  });
});
