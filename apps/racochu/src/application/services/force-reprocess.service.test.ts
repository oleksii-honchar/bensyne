import '@/utils/mastra-rag.test-utils';

import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import * as path from 'path';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { BensyneClient } from '../../infrastructure/services/bensyne-client.service';
import {
  aBensyneClientService,
  aFileChunksInfo,
  aStoredChunkInfo,
} from '../../infrastructure/services/bensyne-client.test-utils';
import { FileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service';
import { aFileMemoryTrackerService } from '../../infrastructure/services/file-memory-tracker.service.test-utils';
import { FileProcessingQueue } from '../../infrastructure/services/file-processing-queue.service';
import { aFileProcessingQueueService } from '../../infrastructure/services/file-processing-queue.test-utils';
import { ProcessFileUseCase } from '../../use-cases/process-file.use-case';
import { aProcessFileUseCase } from '../../use-cases/process-file.use-case.test-utils';
import { Result } from '../../utils/result';
import { mockDirStats, mockDirent, mockFileStats } from '../../utils/test-utils';
import { BatchRunSummary, ForceReprocessService } from './force-reprocess.service';
import {
  aZeroRunSummary,
  heartbeatLinesFrom,
  scriptOutcomesByPath,
  summaryLinesFrom,
  type ScriptedOutcomeKind,
} from './force-reprocess.service.test-utils';

jest.mock('fs/promises');
const fsMock = fsPromises as jest.Mocked<typeof fsPromises>;

describe('ForceReprocessService', () => {
  let service: ForceReprocessService;
  let processFileUseCase: ReturnType<typeof aProcessFileUseCase>;
  let processingQueue: ReturnType<typeof aFileProcessingQueueService>;
  let fileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;
  let bensyneClient: ReturnType<typeof aBensyneClientService>;
  let logger: ReturnType<typeof aLogger>;

  beforeEach(async () => {
    jest.clearAllMocks();
    fsMock.stat.mockReset();
    fsMock.readdir.mockReset();
    fsMock.readFile.mockReset();

    processFileUseCase = aProcessFileUseCase();
    processingQueue = aFileProcessingQueueService();
    fileMemoryTrackerService = aFileMemoryTrackerService();
    bensyneClient = aBensyneClientService();
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ForceReprocessService,
        { provide: ProcessFileUseCase, useValue: processFileUseCase },
        { provide: FileProcessingQueue, useValue: processingQueue },
        { provide: FileMemoryTrackerService, useValue: fileMemoryTrackerService },
        { provide: BensyneClient, useValue: bensyneClient },
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
      fsMock.readdir.mockResolvedValueOnce([mockDirent('sub', true)]).mockResolvedValueOnce([
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
      fsMock.readdir.mockResolvedValue([mockDirent('a.md', false), mockDirent('b.md', false)]);

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
        // T4: force-reprocess paths carry the explicit override flag.
        forceIngest: true,
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
        // T4: resume untracked stays gated (stops the M2 retry loop).
        forceIngest: false,
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
        forceIngest: false,
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
        forceIngest: false,
      });
      expect(processFileUseCase.execute).toHaveBeenNthCalledWith(2, {
        filePath: '/tmp/source-2/untracked.md',
        eventType: 'add',
        sourceId: 'source-2',
        memoryBank: 'source-2',
        sourceConfig: sources[1],
        forceIngest: false,
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

  describe('resumeAll (bank-verified skip logic)', () => {
    it('should skip a tracked file the bank confirms present with chunks (verified skip)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('verified.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(
          aFileChunksInfo({
            chunks: [
              aStoredChunkInfo({ chunkIndex: 0 }),
              aStoredChunkInfo({ chunkIndex: 1 }),
              aStoredChunkInfo({ chunkIndex: 2 }),
            ],
          }),
        ),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).toHaveBeenCalledWith('/tmp/test/verified.md', 'test');
    });

    it('should re-ingest a tracked file the bank reports absent (stale-tracker — the fix)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('stale.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/stale.md',
        eventType: 'add',
        sourceId: 'test',
        memoryBank: 'test',
        sourceConfig: source,
        // T4: bank verification proved loss — the repair must never be gated.
        forceIngest: true,
      });
    });

    it('should process an untracked file without a bank check (new-file regression)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('newfile.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('should skip a tracked file defensively when the bank read errors', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('bank-error.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(Result.ko([new Error('boom')]));

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });

    it('should re-ingest a tracked file the bank reports present with zero chunks (defensive edge)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('empty.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(aFileChunksInfo({ status: 'present', chunks: [] })),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/empty.md',
        eventType: 'add',
        sourceId: 'test',
        memoryBank: 'test',
        sourceConfig: source,
        forceIngest: true,
      });
    });

    it('should re-ingest a tracked file with all chunks memoryStatus: missing (stub rows)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('stub.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(
          aFileChunksInfo({
            chunks: [
              aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'missing' }),
              aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'missing' }),
            ],
          }),
        ),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith({
        filePath: '/tmp/test/stub.md',
        eventType: 'add',
        sourceId: 'test',
        memoryBank: 'test',
        sourceConfig: source,
        forceIngest: true,
      });
    });

    it('should skip a tracked file with mixed chunks (at least one present)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('mixed.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(
          aFileChunksInfo({
            chunks: [
              aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' }),
              aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'missing' }),
              aStoredChunkInfo({ chunkIndex: 2, memoryStatus: 'missing' }),
            ],
          }),
        ),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });

    it('should skip a tracked file with all chunks present', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('healthy.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(
          aFileChunksInfo({
            chunks: [
              aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' }),
              aStoredChunkInfo({ chunkIndex: 1, memoryStatus: 'present' }),
            ],
          }),
        ),
      );

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });
  });

  describe('autoPopulateSources', () => {
    it('should run resume for sources without autoPopulate: false', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.autoPopulateSources(sources);

      // Both sources should be processed (no autoPopulate: false set)
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining('Auto-populating source: id="source-1"'),
      );
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining('Auto-populating source: id="source-2"'),
      );
    });

    it('should skip sources with autoPopulate: false', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1', autoPopulate: true }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2', autoPopulate: false }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.autoPopulateSources(sources);

      // Only source-1 should be processed (source-2 has autoPopulate: false)
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ sourceId: 'source-1' }),
      );
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining('Auto-populating source: id="source-1"'),
      );
      expect(logger.info).not.toHaveBeenCalledWith(
        expect.stringContaining('Auto-populating source: id="source-2"'),
      );
    });

    it('should catch per-source errors without stopping other sources', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat
        .mockRejectedValueOnce(new Error('stat failed')) // source-1 fails
        .mockResolvedValueOnce(mockDirStats()); // source-2 succeeds
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.autoPopulateSources(sources);

      // source-2 should still be processed despite source-1 failing
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ sourceId: 'source-2' }),
      );
    });

    it('should not await queue drain (non-blocking)', async () => {
      const sources = [aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' })];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      // autoPopulateSources should complete after enqueuing, not after queue drains
      await service.autoPopulateSources(sources);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
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
        forceIngest: false,
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
          .map(call => ((call[0] as string).includes('Processing file [') ? (call[0] as string) : null))
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

      it('logs Skipping verified file for resume with the same bracket (bank confirms chunks)', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('tracked.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);
        // Default getFileChunks mock: present + 1 chunk → verified skip.
        bensyneClient.getFileChunks.mockResolvedValue(Result.ok(aFileChunksInfo()));

        await service.resumeAll([source]);

        expect(logger.debug).toHaveBeenCalledWith(
          expect.stringContaining('Skipping verified file for resume [1/1]: path="/tmp/test/tracked.md"'),
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

  describe('multi-root enumeration over resolvedPaths (R1)', () => {
    // The live defect made --force-reprocess/--resume enumerate ONLY
    // source.path (root 0), which is why the shared root was never reached.
    // Enumeration must cover ALL declared roots: union in declared order.

    const aTwoRootSource = (overrides?: { resolvedPaths?: string[]; exclude?: string[] }) =>
      aWatchSourceConfig({
        id: 'agent-persona_simple-session',
        path: '/multi/persona',
        resolvedPaths: overrides?.resolvedPaths ?? ['/multi/persona', '/multi/shared'],
        exclude: overrides?.exclude ?? [],
      });

    it('enumerates the union of both roots in declared order', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('entry.md', false), mockDirent('10-flow', true)])
        .mockResolvedValueOnce([mockDirent('10-step.md', false)])
        .mockResolvedValueOnce([mockDirent('90-archive-latest.md', false)]);

      await service.forceReprocessAll([aTwoRootSource()]);

      const processed = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(processed).toEqual([
        '/multi/persona/entry.md',
        '/multi/persona/10-flow/10-step.md',
        '/multi/shared/90-archive-latest.md',
      ]);
    });

    it('keeps same-named files from different roots as separate entries (no name-clash dedup)', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('x.md', false)]);

      await service.forceReprocessAll([aTwoRootSource({ resolvedPaths: ['/r/one', '/r/two'] })]);

      const processed = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(processed).toEqual(['/r/one/x.md', '/r/two/x.md']);
    });

    it('de-duplicates the same root declared twice (identical absolute paths process once)', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('once.md', false)]);

      await service.forceReprocessAll([aTwoRootSource({ resolvedPaths: ['/dup', '/dup/'] })]);

      const processed = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(processed).toEqual(['/dup/once.md']);
      expect(fsMock.readdir).toHaveBeenCalledTimes(1);
    });

    it('matches exclude globs relative to EACH root (root-relative semantics preserved per root)', async () => {
      // Anchored pattern: matches only root-relative paths. If the scanner
      // (wrongly) computed relPath against root 0 for root 1's entries,
      // '../shared/.skip' would not match and the directory WOULD be read
      // (third readdir call) and its file processed — the expectations below
      // fail only under that bug.
      const source = aTwoRootSource({ exclude: ['.skip/**'] });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        // root 0: a kept file; its top-level excluded dir is never read.
        .mockResolvedValueOnce([mockDirent('keep.md', false), mockDirent('.skip', true)])
        // root 1: same shape relative to root 1 — the excluded dir must be
        // recognized against root 1's own relative paths.
        .mockResolvedValueOnce([mockDirent('share-note.md', false), mockDirent('.skip', true)])
        .mockResolvedValueOnce([mockDirent('hidden-under-root0-relative-bug.md', false)]);

      await service.forceReprocessAll([source]);

      const processed = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(processed).toEqual(['/multi/persona/keep.md', '/multi/shared/share-note.md']);
      expect(fsMock.readdir).toHaveBeenCalledTimes(2);
    });

    it('single-path sources enumerate exactly as before (back-compat literal expectation)', async () => {
      const source = aWatchSourceConfig({ id: 'sessions', path: '/legacy/one-root' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('a.md', false), mockDirent('sub', true)])
        .mockResolvedValueOnce([mockDirent('b.md', false)]);

      await service.forceReprocessAll([source]);

      const processed = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(processed).toEqual(['/legacy/one-root/a.md', '/legacy/one-root/sub/b.md']);
      expect(fsMock.readdir).toHaveBeenCalledTimes(2);
    });
  });

  describe('activity gate in the resume loop (B14a)', () => {
    // Spec §3.3 B14(a): for ttlDays-configured sources each enumerated file is
    // activity-checked BEFORE any getMemoryIds/verify/ingest work; past-due
    // files are skipped with a single notice. ttlDays absent → gate never entered.
    const DAY_MS = 86_400_000;

    // aWatchSourceConfig has no ttlDays override on purpose (Absent = no TTL,
    // config-schemas opt-in); the spread adds the per-source retention directly.
    const aTtlSource = () => ({
      ...aWatchSourceConfig({ id: 'ttl-source', path: '/tmp/ttl-source' }),
      ttlDays: 30,
    });

    // Root stat → directory; enumerated file paths → Stats with the given mtime
    // (the activity clock the gate reads).
    const stubFileMtimes = (mtimes: Map<string, number>): void => {
      fsMock.stat.mockImplementation(async p => {
        const mtimeMs = mtimes.get(String(p));
        if (mtimeMs === undefined) {
          return mockDirStats();
        }
        return { ...mockFileStats(), mtimeMs };
      });
    };

    it('skips a past-due never-tracked file with zero verify/ingest work and a skip notice', async () => {
      const source = aTtlSource();
      stubFileMtimes(new Map([['/tmp/ttl-source/stale.md', Date.now() - 40 * DAY_MS]]));
      fsMock.readdir.mockResolvedValue([mockDirent('stale.md', false)]);
      // Never-tracked: no rows — yet row presence must not matter (OD-5):
      // the gate precedes the tracker lookup entirely.
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      // The contracted observable for B14: the skip notice naming the path.
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringMatching(/Skipping activity-expired file.*stale\.md/),
      );
    });

    it('skips a past-due file whose previously-forgotten row is absent (row presence irrelevant)', async () => {
      const source = aTtlSource();
      const forgottenFile = '/tmp/ttl-source/forgotten.md';
      stubFileMtimes(new Map([[forgottenFile, Date.now() - 90 * DAY_MS]]));
      fsMock.readdir.mockResolvedValue([mockDirent('forgotten.md', false)]);
      // Pre-hard-deleted (forgotten) tracker row: getMemoryIds reads → [] when
      // consulted. The gate must skip before it is ever consulted.
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalledWith(forgottenFile);
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringMatching(/Skipping activity-expired file.*forgotten\.md/),
      );
    });

    it('processes a file with recent mtime normally — row age alone never triggers the skip', async () => {
      const source = aTtlSource();
      const activeFile = '/tmp/ttl-source/active.md';
      // Recent activity (1-day-old mtime) inside the 30-day window; the
      // tracker row behind these memory ids is old by construction — its age
      // must never gate (mtime is the authoritative clock).
      stubFileMtimes(new Map([[activeFile, Date.now() - DAY_MS]]));
      fsMock.readdir.mockResolvedValue([mockDirent('active.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);
      // Bank lost the memories → today's stale-tracker re-ingest branch.
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })),
      );

      await service.resumeAll([source]);

      expect(fileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(activeFile);
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: activeFile }),
      );
      expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('Skipping activity-expired file'));
    });

    it('leaves the call sequence for a ttlDays-less source identical to today (gate not entered, no stat for the gate)', async () => {
      // Gate is defined solely by source.ttlDays; the builder omits it entirely.
      const source = aWatchSourceConfig({ id: 'plain-source', path: '/tmp/plain' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      await service.resumeAll([source]);

      // Today's behavior, byte-for-byte sequence: tracker lookup → execute.
      expect(fileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith('/tmp/plain/untracked.md');
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/plain/untracked.md' }),
      );
      expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('Skipping activity-expired file'));

      // Negative guard: the gate branch must not run — the only stat is the
      // existing source-root stat, never the enumerated file.
      const statTargets = fsMock.stat.mock.calls.map(call => String(call[0]));
      expect(statTargets).not.toContain('/tmp/plain/untracked.md');
      expect(statTargets).toEqual(['/tmp/plain']);
    });

    // NOTE: resume/reprocess paths that reach execute() also carry the
    // forceIngest matrix — see the 'forceIngest propagation (C4 / DEC-A3)'
    // describe at the end of this file.
    it('keeps zero ingest work across repeat resumes of the same past-due set (idempotent w.r.t. restarts)', async () => {
      const source = aTtlSource();
      stubFileMtimes(
        new Map([
          ['/tmp/ttl-source/stale-a.md', Date.now() - 40 * DAY_MS],
          ['/tmp/ttl-source/stale-b.md', Date.now() - 60 * DAY_MS],
        ]),
      );
      fsMock.readdir.mockResolvedValue([mockDirent('stale-a.md', false), mockDirent('stale-b.md', false)]);

      await service.resumeAll([source]);
      await service.resumeAll([source]);

      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
    });
  });

  describe('forceIngest propagation (C4 / DEC-A3)', () => {
    // The execute() params ARE the observable boundary for this task: they are
    // the only input the ProcessFileUseCase hash gate reads (T3 C3).
    interface CapturedParams {
      filePath: string;
      eventType: string;
      forceIngest?: boolean;
    }
    const capturedParams = (): CapturedParams[] =>
      processFileUseCase.execute.mock.calls.map(call => call[0] as CapturedParams);

    const oneFileSource = (id = 'test', root = '/tmp/test') => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('file1.md', false)]);
      return aWatchSourceConfig({ id, path: root });
    };

    describe('force-reprocess entry modes', () => {
      it('forceReprocessAll with {forceIngest:true} ⇒ every execute() carries forceIngest: true', async () => {
        await service.forceReprocessAll([oneFileSource()], { forceIngest: true });

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(true);
      });

      it('forceReprocessAll without opts keeps the operator-override default ⇒ forceIngest: true', async () => {
        // --force-reprocess semantics are unchanged (DEC-A6): the force paths
        // are the designated full-rebuild override even when called directly.
        await service.forceReprocessAll([oneFileSource()]);

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(true);
      });

      it('forceReprocessAll with {forceIngest:false} (the --process-only dispatch) ⇒ forceIngest: false — walk stays gated', async () => {
        await service.forceReprocessAll([oneFileSource()], { forceIngest: false });

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(false);
      });

      it('forceReprocessSource passes the option through — true stays true', async () => {
        const source = oneFileSource('source-1', '/tmp/source-1');
        await service.forceReprocessSource('source-1', [source], { forceIngest: true });

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(true);
      });

      it('forceReprocessSource passes the option through — false stays false (process-only dispatch)', async () => {
        const source = oneFileSource('source-1', '/tmp/source-1');
        await service.forceReprocessSource('source-1', [source], { forceIngest: false });

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(false);
      });

      it('forceReprocessFile (same direct-execute path) carries forceIngest: true by default and with explicit true', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        await service.forceReprocessFile('/tmp/test/one.md', source);
        await service.forceReprocessFile('/tmp/test/two.md', source, { forceIngest: true });

        const params = capturedParams();
        expect(params).toHaveLength(2);
        expect(params[0].forceIngest).toBe(true);
        expect(params[1].forceIngest).toBe(true);
      });
    });

    describe('resume branch split', () => {
      it('stale-tracker branch (bank verification proved loss) ⇒ forceIngest: true — repair never gated (G3)', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });
        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('stale.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1', 'mem-2']);
        bensyneClient.getFileChunks.mockResolvedValue(
          Result.ok(aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })),
        );

        await service.resumeAll([source]);

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].filePath).toBe('/tmp/test/stale.md');
        expect(params[0].forceIngest).toBe(true);
      });

      it('untracked branch ⇒ forceIngest: false — the M2 retry loop is gated', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });
        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

        await service.resumeAll([source]);

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].filePath).toBe('/tmp/test/untracked.md');
        expect(params[0].forceIngest).toBe(false);
      });

      it('healthy verified files stay skipped by the bank check — no execute regardless of the flag (no-change guard)', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });
        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('healthy.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);
        bensyneClient.getFileChunks.mockResolvedValue(
          Result.ok(
            aFileChunksInfo({
              chunks: [aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' })],
            }),
          ),
        );

        await service.resumeAll([source]);

        expect(processFileUseCase.execute).not.toHaveBeenCalled();
      });

      it('untracked via autoPopulateSources (same internal path) ⇒ forceIngest: false too', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });
        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([mockDirent('untracked.md', false)]);
        fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

        await service.autoPopulateSources([source]);

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].forceIngest).toBe(false);
      });
    });
  });

  describe('C8 per-run summary (T6 / spec C8)', () => {
    // The counter machine is tested as DATA: the summary the run composes and
    // returns must equal the scripted outcome counts. The line itself is only
    // format-asserted once per prefix (narrow log-format exception).
    const ROOT = '/tmp/c8';
    const fileAt = (name: string) => `${ROOT}/${name}`;

    const c8Source = (id = 'c8-source', root = ROOT) => aWatchSourceConfig({ id, path: root });

    const enumerate = (...names: string[]) => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue(names.map(n => mockDirent(n, false)));
    };

    const bankStateOf = (stateOf: Record<string, 'healthy' | 'lost'>) => {
      bensyneClient.getFileChunks.mockImplementation(async (filePath: string) =>
        Result.ok(
          stateOf[filePath] === 'lost'
            ? aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })
            : aFileChunksInfo({
                chunks: [aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' })],
              }),
        ),
      );
    };

    it('resume run: returned summary DATA equals the scripted outcome mix', async () => {
      // Scripted stream: real ingest (with memoryIds), hash-gate skip,
      // terminal skip — both from the untracked branch through execute();
      // a loop-level verified-healthy skip; and a stale-tracker forced re-ingest.
      enumerate('a-fresh.md', 'b-gated.md', 'c-terminal.md', 'd-verified.md', 'e-stale.md');
      fileMemoryTrackerService.getMemoryIds.mockImplementation(async (filePath: string) =>
        filePath === fileAt('d-verified.md')
          ? ['mem-keep-1']
          : filePath === fileAt('e-stale.md')
            ? ['mem-lost-1']
            : [],
      );
      bankStateOf({ [fileAt('d-verified.md')]: 'healthy', [fileAt('e-stale.md')]: 'lost' });
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('a-fresh.md')]: 'ingest',
        [fileAt('b-gated.md')]: 'gated-skip',
        [fileAt('c-terminal.md')]: 'terminal-skip',
        [fileAt('e-stale.md')]: 'ingest',
      });

      const summary: BatchRunSummary = await service.resumeAll([c8Source()]);

      expect(summary).toEqual({
        files: 4, // execute() calls only — the verified-healthy skip never reaches it
        gatedSkips: 1,
        terminalSkipSkips: 1,
        verifiedSkips: 1,
        reIngested: 2, // fresh ingest + stale-tracker forced re-ingest
      });
    });

    it('resume summary accumulates across sources of one run', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('gated.md', false), mockDirent('ingest.md', false)])
        .mockResolvedValueOnce([mockDirent('verified.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockImplementation(async (filePath: string) =>
        filePath === '/tmp/c8-1/verified.md' ? ['mem-keep-1'] : [],
      );
      bankStateOf({ '/tmp/c8-1/verified.md': 'healthy' });
      scriptOutcomesByPath(processFileUseCase.execute, {
        '/tmp/c8-0/gated.md': 'gated-skip',
        '/tmp/c8-0/ingest.md': 'ingest',
      });

      const summary = await service.resumeAll([c8Source('c8-0', '/tmp/c8-0'), c8Source('c8-1', '/tmp/c8-1')]);

      expect(summary).toEqual({
        files: 2,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 1,
        reIngested: 1,
      });
    });

    it('single-source run (resumeSource) still composes and returns the summary', async () => {
      const sources = [c8Source('c8-0'), c8Source('keep-me')];
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('gated.md', false)]);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('gated.md')]: 'gated-skip' });

      const summary = await service.resumeSource('c8-0', sources);

      expect(summary).toEqual({
        files: 1,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 0,
      });
      expect(summaryLinesFrom(logger.info)).toEqual([
        'resume finished: files=1, gated-skips=1, terminal-skip-skips=0, verified-skips=0, re-ingested=0',
      ]);
    });

    it('auto-populate run (resume shape) composes and logs the summary', async () => {
      // Spec §9 (amended): the flat C8 summary of the auto-populate pass IS
      // the acceptance check — the run path must carry the summary too.
      enumerate('gated.md', 'verified.md');
      fileMemoryTrackerService.getMemoryIds.mockImplementation(async (filePath: string) =>
        filePath === fileAt('verified.md') ? ['mem-keep-1'] : [],
      );
      bankStateOf({ [fileAt('verified.md')]: 'healthy' });
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('gated.md')]: 'gated-skip' });

      const summary = await service.autoPopulateSources([c8Source()]);

      expect(summary).toEqual({
        files: 1,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 1,
        reIngested: 0,
      });
      expect(summaryLinesFrom(logger.info)).toEqual([
        'resume finished: files=1, gated-skips=1, terminal-skip-skips=0, verified-skips=1, re-ingested=0',
      ]);
    });

    it('failed outcomes count as files only (never as a skip or a re-ingest)', async () => {
      enumerate('broken.md');
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('broken.md')]: 'failure' });

      const summary = await service.resumeAll([c8Source()]);

      // Counted as a processed file — NOT as a skip and NOT as a re-ingest.
      expect(summary).toEqual({
        files: 1,
        gatedSkips: 0,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 0,
      });
    });

    it('force-reprocess run summary uses the force-reprocess prefix, same tokens', async () => {
      enumerate('a.md', 'b.md');
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('a.md')]: 'ingest',
        [fileAt('b.md')]: 'ingest',
      });

      const summary = await service.forceReprocessAll([c8Source()]);

      expect(summary).toEqual({
        files: 2,
        gatedSkips: 0,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 2,
      });
      expect(summaryLinesFrom(logger.info)).toEqual([
        'force-reprocess finished: files=2, gated-skips=0, terminal-skip-skips=0, verified-skips=0, re-ingested=2',
      ]);
    });

    it('process-only walk (forceIngest:false) classifies gated and terminal skips', async () => {
      // The process-only dispatch runs the SAME batch path with the gate on,
      // so the same tokens classify its outcomes — no separate vocabulary.
      enumerate('gate-hit.md', 'skip-row.md', 'changed.md');
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('gate-hit.md')]: 'gated-skip',
        [fileAt('skip-row.md')]: 'terminal-skip',
        [fileAt('changed.md')]: 'ingest',
      });

      const summary = await service.forceReprocessAll([c8Source()], { forceIngest: false });

      expect(summary).toEqual({
        files: 3,
        gatedSkips: 1,
        terminalSkipSkips: 1,
        verifiedSkips: 0,
        reIngested: 1,
      });
    });

    it('zero-activity runs still log zero-value summaries (flat summaries are the signal)', async () => {
      enumerate();
      const resumeSummary = await service.resumeAll([c8Source()]);

      expect(resumeSummary).toEqual(aZeroRunSummary());
      expect(summaryLinesFrom(logger.info)).toEqual([
        'resume finished: files=0, gated-skips=0, terminal-skip-skips=0, verified-skips=0, re-ingested=0',
      ]);

      logger.info.mockClear();
      const forceSummary = await service.forceReprocessAll([c8Source()]);

      expect(forceSummary).toEqual(aZeroRunSummary());
      expect(summaryLinesFrom(logger.info)).toEqual([
        'force-reprocess finished: files=0, gated-skips=0, terminal-skip-skips=0, verified-skips=0, re-ingested=0',
      ]);
    });

    it('emits exactly one summary line per completed run (prefix token + key order)', async () => {
      enumerate('b-gated.md');
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('b-gated.md')]: 'gated-skip' });

      await service.resumeAll([c8Source()]);

      const lines = summaryLinesFrom(logger.info);
      expect(lines).toHaveLength(1);
      expect(lines[0]).toMatch(
        /^resume finished: files=\d+, gated-skips=\d+, terminal-skip-skips=\d+, verified-skips=\d+, re-ingested=\d+$/,
      );
      expect(lines[0]).toBe(
        'resume finished: files=1, gated-skips=1, terminal-skip-skips=0, verified-skips=0, re-ingested=0',
      );
    });

    it('source-not-found early exits are untouched — no run, no summary', async () => {
      const sources = [c8Source('real')];

      await service.resumeSource('missing', sources);
      await service.forceReprocessSource('missing', sources);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(summaryLinesFrom(logger.info)).toEqual([]);
    });
  });

  describe('progress heartbeat in batch loops (Ad-Hoc F — operator visibility)', () => {
    // The payfit incident: a --resume over 8304 files ran 45+ minutes emitting
    // nothing between "Files found for resume" and the final summary (healthy
    // files log only at DEBUG). The heartbeat line IS the user-visible feature:
    // its format is pinned under the narrow C8/T6 log-contract exception
    // (one format test per prefix); cadence and counting tests pin the exact
    // cumulative strings from independently computed milestones.
    const RESUME_HB_RE =
      /^resume progress: \d+\/\d+ processed \(verified=\d+, gated=\d+, stale-repair=\d+, untracked=\d+, failures=\d+\)$/;
    const FORCE_HB_RE =
      /^force-reprocess progress: \d+\/\d+ processed \(verified=\d+, gated=\d+, stale-repair=\d+, untracked=\d+, failures=\d+\)$/;

    const HB_ROOT = '/tmp/hb';
    const hbName = (n: number) => `file-${String(n).padStart(3, '0')}.md`;
    const hbPath = (n: number) => `${HB_ROOT}/${hbName(n)}`;
    const hbIndex = (filePath: string) => Number(/file-(\d+)\.md$/.exec(filePath)?.[1] ?? NaN);
    const hbSource = () => aWatchSourceConfig({ id: 'hb-source', path: HB_ROOT });

    const enumerateHb = (count: number) => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue(
        Array.from({ length: count }, (_, i) => mockDirent(hbName(i + 1), false)),
      );
    };

    // Deterministic role assignment for the mixed stream (pairwise-disjoint
    // residues: verified≡0 mod 50, stale≡7 mod 100, failure≡3 mod 50, gated≡11 mod 25).
    const isVerifiedAt = (n: number) => n % 50 === 0; // bank-verified healthy skip (never executes)
    const isStaleAt = (n: number) => n % 100 === 7; // stale-tracker branch pre-classification
    const isFailureAt = (n: number) => n % 50 === 3; // execute → Result.ko
    const isGatedAt = (n: number) => n % 25 === 11; // execute → ok + skipped='unchanged'

    const countUpTo = (pred: (n: number) => boolean, limit: number): number => {
      let total = 0;
      for (let n = 1; n <= limit; n++) {
        if (pred(n)) total += 1;
      }
      return total;
    };

    const scriptResumeRoles = (count: number) => {
      enumerateHb(count);
      fileMemoryTrackerService.getMemoryIds.mockImplementation(async (filePath: string) => {
        const n = hbIndex(filePath);
        return isVerifiedAt(n) || isStaleAt(n) ? [`mem-tracker-${n}`] : [];
      });
      bensyneClient.getFileChunks.mockImplementation(async (filePath: string) =>
        Result.ok(
          isStaleAt(hbIndex(filePath))
            ? aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })
            : aFileChunksInfo({
                chunks: [aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' })],
              }),
        ),
      );
      const script: Record<string, ScriptedOutcomeKind> = {};
      for (let n = 1; n <= count; n++) {
        if (isVerifiedAt(n)) continue; // verified-healthy files never reach execute()
        script[hbPath(n)] = isFailureAt(n) ? 'failure' : isGatedAt(n) ? 'gated-skip' : 'ingest';
      }
      scriptOutcomesByPath(processFileUseCase.execute, script);
    };

    const scriptForceRoles = (count: number) => {
      enumerateHb(count);
      const script: Record<string, ScriptedOutcomeKind> = {};
      for (let n = 1; n <= count; n++) {
        script[hbPath(n)] = isFailureAt(n) ? 'failure' : isGatedAt(n) ? 'gated-skip' : 'ingest';
      }
      scriptOutcomesByPath(processFileUseCase.execute, script);
    };

    const withNoRoles = (count: number) => {
      enumerateHb(count);
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      // scriptOutcomesByPath default → every file is an ordinary successful ingest.
      scriptOutcomesByPath(processFileUseCase.execute, {});
    };

    const resumeHeartbeat = (
      processed: number,
      total: number,
      fields: [verified: number, gated: number, stale: number, untracked: number, failures: number],
    ) =>
      `resume progress: ${processed}/${total} processed (verified=${fields[0]}, gated=${fields[1]}, stale-repair=${fields[2]}, untracked=${fields[3]}, failures=${fields[4]})`;

    const forceHeartbeat = (processed: number, total: number, gated: number, failures: number) =>
      `force-reprocess progress: ${processed}/${total} processed (verified=0, gated=${gated}, stale-repair=0, untracked=0, failures=${failures})`;

    // Cumulative field values for the resume role-stream at milestone k — read
    // straight off the role definitions (pairwise disjoint, so untracked =
    // everything the loop classifies into neither verified nor stale).
    const fieldsAt = (k: number): [number, number, number, number, number] => {
      const verified = countUpTo(isVerifiedAt, k);
      const stale = countUpTo(isStaleAt, k);
      const gated = countUpTo(isGatedAt, k);
      const failures = countUpTo(isFailureAt, k);
      const untracked = k - verified - stale;
      return [verified, gated, stale, untracked, failures];
    };

    it('resumes of 250 mixed files emit heartbeats EXACTLY at 100 and 200 with correct cumulative fields (none at 50/150/250)', async () => {
      scriptResumeRoles(250);

      await service.resumeAll([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([
        resumeHeartbeat(100, 250, fieldsAt(100)),
        resumeHeartbeat(200, 250, fieldsAt(200)),
      ]);
    });

    it('a run of exactly 100 files emits one 100/100 heartbeat and then only the normal final summary (no duplicate)', async () => {
      scriptResumeRoles(100);

      await service.resumeAll([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([resumeHeartbeat(100, 100, fieldsAt(100))]);
      expect(summaryLinesFrom(logger.info)).toEqual([
        'resume finished: files=98, gated-skips=4, terminal-skip-skips=0, verified-skips=2, re-ingested=92',
      ]);
    });

    it('runs below 100 files emit zero heartbeats in either loop, per-file log volume unchanged (count-probe)', async () => {
      scriptResumeRoles(99);
      await service.resumeAll([hbSource()]);
      expect(heartbeatLinesFrom(logger.info)).toEqual([]);

      scriptForceRoles(99);
      await service.forceReprocessAll([hbSource()]);
      expect(heartbeatLinesFrom(logger.info)).toEqual([]);
      // Unchanged per-file volume: the existing per-file INFO still fires
      // exactly once per processed file, and NOTHING else was added.
      const perFileProcessLines = logger.info.mock.calls
        .map(call => String(call[0]))
        .filter(line => line.startsWith('Processing file [')).length;
      expect(perFileProcessLines).toBe(99);
    });

    it('resume progress line matches the contracted format exactly (format contract, resume prefix)', async () => {
      withNoRoles(130);

      await service.resumeAll([hbSource()]);

      const lines = heartbeatLinesFrom(logger.info);
      expect(lines).toEqual([
        'resume progress: 100/130 processed (verified=0, gated=0, stale-repair=0, untracked=100, failures=0)',
      ]);
      expect(lines[0]).toMatch(RESUME_HB_RE);
    });

    it('process-only walk of the force-reprocess loop mirrors the field list under the force prefix — non-zero outcomes count, branch fields stay 0 (format contract)', async () => {
      scriptForceRoles(250);

      // Run with forceIngest:false — the --process-only dispatch. The prefix is
      // produced by the loop, not the flag: force-reprocess entries share this
      // exact code path (single newLoopProgress call site), so the same
      // contract holds for both — documented shared-path argument.
      await service.forceReprocessAll([hbSource()], { forceIngest: false });

      const lines = heartbeatLinesFrom(logger.info);
      expect(lines).toEqual([
        forceHeartbeat(100, 250, countUpTo(isGatedAt, 100), countUpTo(isFailureAt, 100)),
        forceHeartbeat(200, 250, countUpTo(isGatedAt, 200), countUpTo(isFailureAt, 200)),
      ]);
      for (const line of lines) {
        expect(line).toMatch(FORCE_HB_RE);
      }
    });

    it('auto-populate passes the resume prefix to its heartbeats (same loop, shared signal)', async () => {
      scriptResumeRoles(150);

      await service.autoPopulateSources([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([resumeHeartbeat(100, 150, fieldsAt(100))]);
    });

    it('field provenance: terminal-skip files never appear as a heartbeat field; stale/untracked are branch classifications; ko adds failures on top', async () => {
      // Files 1–3 are bank-verified healthy; 97 untracked files reach execute
      // (1 terminal-skip, 1 gated, 1 ko, 94 ingests). At processed=100 the
      // line carries: verified=3, gated=1, stale-repair=0, untracked=97
      // (ALL non-verified branch files — terminal-skip and ko files included,
      // that is their branch), failures=1. The terminal-skip file contributes
      // to no field of its own; a stale-branch ko would count in BOTH
      // stale-repair and failures (documented overlap semantics).
      enumerateHb(100);
      fileMemoryTrackerService.getMemoryIds.mockImplementation(async (filePath: string) => {
        const n = hbIndex(filePath);
        return n <= 3 ? [`mem-tracker-${n}`] : [];
      });
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(
          aFileChunksInfo({ chunks: [aStoredChunkInfo({ chunkIndex: 0, memoryStatus: 'present' })] }),
        ),
      );
      scriptOutcomesByPath(processFileUseCase.execute, {
        [hbPath(97)]: 'terminal-skip',
        [hbPath(98)]: 'gated-skip',
        [hbPath(99)]: 'failure',
      });

      await service.resumeAll([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([resumeHeartbeat(100, 100, [3, 1, 0, 97, 1])]);
    });

    it('per-loop heartbeats reset per source run: a 60-file second source adds no heartbeat (loop-local processed)', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'hb-1', path: '/tmp/hb-1' }),
        aWatchSourceConfig({ id: 'hb-2', path: '/tmp/hb-2' }),
      ];
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce(Array.from({ length: 150 }, (_, i) => mockDirent(hbName(i + 1), false)))
        .mockResolvedValueOnce(Array.from({ length: 60 }, (_, i) => mockDirent(hbName(i + 1), false)));
      fileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      scriptOutcomesByPath(processFileUseCase.execute, {});

      await service.resumeAll(sources);

      // Source 1 (150 files): ONE heartbeat at its own 100 with total=150.
      // Source 2 (60 files): below its loop threshold — nothing.
      expect(heartbeatLinesFrom(logger.info)).toEqual([
        'resume progress: 100/150 processed (verified=0, gated=0, stale-repair=0, untracked=100, failures=0)',
      ]);
    });

    it('source-not-found early exits log no heartbeat (untouched early-exit path)', async () => {
      await service.resumeSource('missing', [hbSource()]);
      await service.forceReprocessSource('missing', [hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([]);
    });
  });
});
