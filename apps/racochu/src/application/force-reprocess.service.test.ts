import '@/utils/mastra-rag.test-utils';

import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import * as path from 'path';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { aFileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service.test-utils';
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
  let fileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;
  let logger: ReturnType<typeof aLogger>;

  beforeEach(async () => {
    jest.clearAllMocks();
    fsMock.stat.mockReset();
    fsMock.readdir.mockReset();
    fsMock.readFile.mockReset();

    processFileUseCase = aProcessFileUseCase();
    processingQueue = aFileProcessingQueueService();
    fileMemoryTrackerService = aFileMemoryTrackerService();
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ForceReprocessService,
        { provide: ProcessFileUseCase, useValue: processFileUseCase },
        { provide: FileProcessingQueue, useValue: processingQueue },
        { provide: FileMemoryTrackerService, useValue: fileMemoryTrackerService },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    service = module.get<ForceReprocessService>(ForceReprocessService);
  });

  describe('forceReprocessAll', () => {
    it('should process files from all sources via direct execute calls', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1' }), aWatchSourceConfig({ id: 'source-2' })];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      await service.forceReprocessAll(sources);

      // 2 sources × 1 file each = 2 direct execute calls (not via the queue)
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should call execute for each file found in each source', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' })];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

      await service.forceReprocessAll(sources);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });
  });

  describe('forceReprocessSource', () => {
    it('should process files from specific source by id via direct execute', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      await service.forceReprocessSource('source-1', sources);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should not execute when source not found', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1' })];

      await service.forceReprocessSource('non-existent', sources);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
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

    it('should not execute files when path is not a directory', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockFileStats());

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should not execute files when stat fails', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockRejectedValue(new Error('ENOENT'));

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should not execute files for an empty source', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([]);

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });
  });

  describe('exclude patterns (glob-matcher migration regression)', () => {
    it('skips a directory matching **/X/** and processes files outside it', async () => {
      const source = aWatchSourceConfig({
        id: 'test',
        path: '/tmp/test',
        exclude: ['**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([
          mockDirent('tool-responses', true), // excluded directory
          mockDirent('normal', true), // kept directory
        ])
        .mockResolvedValueOnce([mockDirent('kept.md', false)]); // normal/kept.md

      await service.forceReprocessAll([source]);

      // Only the file outside the excluded directory is processed.
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/test/normal/kept.md' }),
      );
    });

    it('excludes a top-level directory named per the pattern', async () => {
      const source = aWatchSourceConfig({
        id: 'test',
        path: '/tmp/test',
        exclude: ['**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('tool-responses', true), // excluded top-level directory
        mockDirent('file.md', false), // kept top-level file
      ]);

      await service.forceReprocessAll([source]);

      // Only the top-level file is processed; the excluded directory is never scanned.
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/test/file.md' }),
      );
    });

    it('excludes files inside a nested directory matching the pattern', async () => {
      const source = aWatchSourceConfig({
        id: 'test',
        path: '/tmp/test',
        exclude: ['**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('sub', true)])
        .mockResolvedValueOnce([
          mockDirent('tool-responses', true), // nested excluded directory
          mockDirent('kept.md', false), // nested kept file
        ]);

      await service.forceReprocessAll([source]);

      // Only the kept file is processed; the nested excluded directory is skipped.
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/test/sub/kept.md' }),
      );
    });

    it('processes all files when none match an exclude pattern', async () => {
      const source = aWatchSourceConfig({
        id: 'test',
        path: '/tmp/test',
        exclude: ['**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('a.md', false),
        mockDirent('b.md', false),
      ]);

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
    });

    it('honors multiple exclude patterns', async () => {
      const source = aWatchSourceConfig({
        id: 'test',
        path: '/tmp/test',
        exclude: ['**/node_modules/**', '**/tool-responses/**'],
      });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([
          mockDirent('node_modules', true), // excluded (pattern 1)
          mockDirent('tool-responses', true), // excluded (pattern 2)
          mockDirent('src', true), // kept
        ])
        .mockResolvedValueOnce([mockDirent('index.ts', false)]); // src/index.ts

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/test/src/index.ts' }),
      );
    });
  });

  describe('direct execution (new contract)', () => {
    it('should call execute directly for each file with correct args', async () => {
      const source = aWatchSourceConfig({ id: 'my-source', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      await service.forceReprocessAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/file1.md',
        eventType: 'add',
        sourceId: 'my-source',
        memoryBank: 'my-source',
        sourceConfig: source,
      });
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should call execute sequentially — file N+1 only after file N resolves', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

      // Track the order in which execute resolves for each file.
      // file1 is made slower than file2: if the service fired both in parallel
      // (without awaiting each), file2 could resolve first.
      const resolutionOrder: string[] = [];
      processFileUseCase.execute.mockImplementation(async params => {
        const filePath = (params as { filePath: string }).filePath;
        const delay = filePath.includes('file1.md') ? 30 : 5;
        await new Promise(resolve => setTimeout(resolve, delay));
        resolutionOrder.push(filePath);
        return Result.ok(undefined as unknown as void);
      });

      await service.forceReprocessAll([source]);

      // Sequential await guarantees file1 resolves before file2 starts.
      expect(resolutionOrder).toEqual(['/tmp/test/file1.md', '/tmp/test/file2.md']);
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
    });

    it('should handle file reprocessing failure gracefully without throwing', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

      processFileUseCase.execute.mockResolvedValue(Result.ko([new Error('Processing failed')]));

      // A Result.ko from execute must not throw — the service logs and continues.
      await expect(service.forceReprocessAll([source])).resolves.not.toThrow();
      expect(processingQueue.addToQueue).not.toHaveBeenCalled();
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

  describe('resumeAll (tracker-only heuristic)', () => {
    it('should skip a file that already has memories', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('tracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });

    it('should process a file that has no memories', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/untracked.md',
        eventType: 'add',
        sourceId: 'test',
        memoryBank: 'test',
        sourceConfig: source,
      });
    });

    it('should only process files without memories in a mixed set', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('tracked.md', false), mockDirent('untracked.md', false)]);
      // First file has memories (skip), second has none (process).
      fileMemoryTrackerService.getMemoryIds.mockResolvedValueOnce(['mem-1']).mockResolvedValueOnce([]);

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/untracked.md',
        eventType: 'add',
        sourceId: 'test',
        memoryBank: 'test',
        sourceConfig: source,
      });
    });

    it('should not read the file or chunk it for the decision', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      // The decision must be a pure tracker lookup — no file read for the decision.
      expect(fsMock.readFile).not.toHaveBeenCalled();
    });

    it('should process untracked files from all sources via direct execute calls', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll(sources);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(processFileUseCase.execute).toHaveBeenNthCalledWith(1, {
        filePath: '/tmp/source-1/untracked.md',
        eventType: 'add',
        sourceId: 'source-1',
        memoryBank: 'source-1',
        sourceConfig: sources[0],
      });
      expect(processFileUseCase.execute).toHaveBeenNthCalledWith(2, {
        filePath: '/tmp/source-2/untracked.md',
        eventType: 'add',
        sourceId: 'source-2',
        memoryBank: 'source-2',
        sourceConfig: sources[1],
      });
    });

    it('should skip a file when the tracker read throws', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('error.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockRejectedValue(new Error('tracker error'));

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });
  });

  describe('resumeSource', () => {
    it('should process untracked files from the requested source by id', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeSource('source-2', sources);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/source-2/untracked.md',
        eventType: 'add',
        sourceId: 'source-2',
        memoryBank: 'source-2',
        sourceConfig: sources[1],
      });
    });

    it('should not execute when the source is not found', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' })];

      await service.resumeSource('non-existent', sources);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });
  });

  describe('forceReprocess log queue position [idx/totalFilesInQueue] (DEC-0068)', () => {
    describe('processSource', () => {
      it('logs Processing file [i/totalFilesInQueue] before each execute (1-based)', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

        await service.forceReprocessAll([source]);

        expect(logger.info).toHaveBeenCalledWith(
          expect.stringContaining('Processing file [1/2]: path="/tmp/test/file1.md"'),
        );
        expect(logger.info).toHaveBeenCalledWith(
          expect.stringContaining('Processing file [2/2]: path="/tmp/test/file2.md"'),
        );
      });

      it('verifies 1-based indexing — first file is [1/N], not [0/N]', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('only.md', false)]);

        await service.forceReprocessAll([source]);

        expect(logger.info).toHaveBeenCalledWith(
          expect.stringContaining('Processing file [1/1]: path="/tmp/test/only.md"'),
        );
        expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('Processing file [0/1]'));
      });

      it('logs File reprocessing failed [i/totalFilesInQueue] on execute failure', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);

        processFileUseCase.execute.mockResolvedValue(Result.ko([new Error('Processing failed')]));

        await service.forceReprocessAll([source]);

        expect(logger.error).toHaveBeenCalledWith(
          expect.stringContaining('File reprocessing failed [1/1]: path="/tmp/test/file1.md"'),
        );
      });

      it('logs execute in sequential 1-based order [1/2] then [2/2]', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false), mockDirent('file2.md', false)]);

        await service.forceReprocessAll([source]);

        const processingLogs = logger.info.mock.calls
          .map(call => (call[0] as string).includes('Processing file [')
            ? (call[0] as string)
            : null)
          .filter((entry): entry is string => entry !== null);

        expect(processingLogs).toEqual([
          'Processing file [1/2]: path="/tmp/test/file1.md"',
          'Processing file [2/2]: path="/tmp/test/file2.md"',
        ]);
      });
    });

    describe('resumeSourceInternal', () => {
      it('logs Resuming untracked file [i/totalFilesInQueue] before execute', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

        await service.resumeAll([source]);

        expect(logger.info).toHaveBeenCalledWith(
          expect.stringContaining('Resuming untracked file [1/1]: path="/tmp/test/untracked.md"'),
        );
      });

      it('logs Skipping tracked file for resume with the same bracket', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('tracked.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);

        await service.resumeAll([source]);

        expect(logger.debug).toHaveBeenCalledWith(
          expect.stringContaining(
            'Skipping tracked file for resume [1/1]: path="/tmp/test/tracked.md"',
          ),
        );
      });

      it('logs Skipping file for resume; failed to read stored memory count with the same bracket', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('error.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockRejectedValue(new Error('tracker error'));

        await service.resumeAll([source]);

        expect(logger.warn).toHaveBeenCalledWith(
          expect.stringContaining(
            'Skipping file for resume; failed to read stored memory count [1/1]: path="/tmp/test/error.md"',
          ),
        );
      });
    });
  });
});
