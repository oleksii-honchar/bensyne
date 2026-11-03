import '@/utils/mastra-rag.test-utils';

import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import * as path from 'path';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { FileTrackerRepository } from '../../infrastructure/repositories/file-tracker.repository';
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
  aFileTrackerRow,
  aZeroRunSummary,
  heartbeatLinesFrom,
  scriptKnownRows,
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
  let fileTrackerRepository: { findTrackedBySourceId: jest.Mock };
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
    // T10 queue-subtraction seam (same fake shape as recover.service.test.ts):
    // default = no rows (all files new). Tests script rows per source.
    fileTrackerRepository = { findTrackedBySourceId: jest.fn().mockResolvedValue([]) };
    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ForceReprocessService,
        { provide: ProcessFileUseCase, useValue: processFileUseCase },
        { provide: FileProcessingQueue, useValue: processingQueue },
        { provide: FileMemoryTrackerService, useValue: fileMemoryTrackerService },
        { provide: BensyneClient, useValue: bensyneClient },
        { provide: FileTrackerRepository, useValue: fileTrackerRepository },
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

  describe('resumeAll (new-files-only queue — T10 / DEC-A7)', () => {
    // Amended C4: queue = enumerated files with NO FileTracker row at all
    // (terminal-skip rows ARE rows → known). One findTrackedBySourceId call
    // per source; zero per-file getMemoryIds/getFileChunks reads.
    const rowFor = (name: string, root = '/tmp/test') => aFileTrackerRow(`${root}/${name}`);

    it('AC1 mixed 4-file corpus: normal row + skip-row + 2 never-seen ⇒ execute ONLY for the never-seen, zero bank/tracker reads', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('normal-row.md', false),
        mockDirent('skip-row.md', false),
        mockDirent('fresh-a.md', false),
        mockDirent('fresh-b.md', false),
      ]);
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([
        rowFor('normal-row.md'),
        aFileTrackerRow('/tmp/test/skip-row.md', { skipReason: 'content-filtered' }),
      ]);

      await service.resumeAll([source]);

      // ONE seam call per source, never per-file.
      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledTimes(1);
      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledWith('test');

      const queued = processFileUseCase.execute.mock.calls.map(
        call => (call[0] as { filePath: string }).filePath,
      );
      expect(queued).toEqual(['/tmp/test/fresh-a.md', '/tmp/test/fresh-b.md']);

      // The retired classifiers: zero calls on the resume path (AC1 guard).
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('operator visibility: emits `Resume queue built: source=…, enumerated=…, known=…, new=` once per source with the exact queue arithmetic (reviewer in-review pin — T10 accepted deviation is README-documented, plan Global rule 2: one contract test per operator string)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('normal-row.md', false),
        mockDirent('fresh-a.md', false),
        mockDirent('fresh-b.md', false),
      ]);
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([rowFor('normal-row.md')]);

      await service.resumeAll([source]);

      const queueLines = logger.info.mock.calls
        .map(call => String(call[0]))
        .filter(line => line.includes('Resume queue built:'));
      // ONE line per source, exact contract-shaped fields: 3 enumerated,
      // 1 known by row, 2 new — the arithmetic the §11 repeat-run
      // measurements depend on.
      expect(queueLines).toEqual(['Resume queue built: source="test", enumerated=3, known=1, new=2']);
    });

    it('AC2 known file whose stored hash differs from current content is NOT queued (row presence alone decides; hash never read)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('changed-on-disk.md', false)]);
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, ['/tmp/test/changed-on-disk.md'], {
        hashOf: '/tmp/test/changed-on-disk.md',
      });

      await service.resumeAll([source]);

      // Content-changed known files are RECOVER's duty (DEC-A7 guarantee (b)),
      // never resume's: no queue entry, and the hash is not even consulted.
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('AC3+AC4 every queued execute carries forceIngest explicitly present-and-false (captured literals; defense-in-depth pin per DEC-A3/A7)', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([
        mockDirent('known.md', false),
        mockDirent('fresh-a.md', false),
        mockDirent('fresh-b.md', false),
      ]);
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, ['/tmp/test/known.md']);

      await service.resumeAll([source]);

      const params = processFileUseCase.execute.mock.calls.map(call => call[0] as Record<string, unknown>);
      expect(params).toHaveLength(2);
      for (const p of params) {
        // Present AND false: a queue change that drops the explicit flag must
        // fail this pin even though an absent flag would behave identically
        // today (the gate default) — that silent drift is what we guard.
        expect(Object.hasOwn(p, 'forceIngest')).toBe(true);
        expect(p.forceIngest).toBe(false);
      }
      // The gate itself stays the use-case's responsibility (faked seam ⇒
      // the flag reaches execute verbatim; internal hash-gate untouched).
      expect(params[0].filePath).toBe('/tmp/test/fresh-a.md');
      expect(params[1].filePath).toBe('/tmp/test/fresh-b.md');
    });

    it('should not read or hash a queued file for the queueing decision', async () => {
      const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('fresh.md', false)]);

      await service.resumeAll([source]);

      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      // The decision is a pure row-set subtraction — no file read.
      expect(fsMock.readFile).not.toHaveBeenCalled();
    });

    it('should queue new files from all sources with one row-set call per source', async () => {
      const sources = [
        aWatchSourceConfig({ id: 'source-1', path: '/tmp/source-1' }),
        aWatchSourceConfig({ id: 'source-2', path: '/tmp/source-2' }),
      ];

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('fresh.md', false)]);

      await service.resumeAll(sources);

      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledTimes(2);
      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenNthCalledWith(1, 'source-1');
      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenNthCalledWith(2, 'source-2');
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(processFileUseCase.execute).toHaveBeenNthCalledWith(1, {
        filePath: '/tmp/source-1/fresh.md',
        eventType: 'add',
        sourceId: 'source-1',
        memoryBank: 'source-1',
        sourceConfig: sources[0],
        forceIngest: false,
      });
      expect(processFileUseCase.execute).toHaveBeenNthCalledWith(2, {
        filePath: '/tmp/source-2/fresh.md',
        eventType: 'add',
        sourceId: 'source-2',
        memoryBank: 'source-2',
        sourceConfig: sources[1],
        forceIngest: false,
      });
    });
  });

  describe('resumeAll (bank verification retired — T10 / DEC-A7)', () => {
    // The bank-verification block (getFileChunks × isFileHealthy + isKo()
    // defensive skip + verified-skip counting) is DELETED from the resume
    // path. Its whole old vocabulary (healthy/stale/zero-chunks/stub/mixed
    // chunk states) must now be invisible to the resume loop: row-present
    // files are excluded by the row set ALONE. Bank-loss repair belongs to
    // --recover (DEC-A7 guarantee (a)) — pinned by recover suites, not here.
    const rowFile = (name: string) => aFileTrackerRow(`/tmp/test/${name}`);

    const enumerateOne = (name: string) => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent(name, false)]);
    };

    it('a healthy row-present file is never queued and never bank-queried (verification retired)', async () => {
      enumerateOne('known-healthy.md');
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([rowFile('known-healthy.md')]);
      // Bank WOULD report healthy — must not be consulted at all.
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

      await service.resumeAll([aWatchSourceConfig({ id: 'test', path: '/tmp/test' })]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
    });

    it('a row-present file the bank lost (old stale-tracker repair target) is NOT queued and NOT bank-queried', async () => {
      enumerateOne('bank-lost.md');
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([rowFile('bank-lost.md')]);
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(aFileChunksInfo({ status: 'FILE_NOT_FOUND', chunks: [] })),
      );

      await service.resumeAll([aWatchSourceConfig({ id: 'test', path: '/tmp/test' })]);

      // Old behavior: re-ingest with forceIngest:true. New contract: recover's job.
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('a row-present file whose bank read errors is NOT queued — the isKo() defensive skip retired with the read', async () => {
      enumerateOne('bank-error.md');
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([rowFile('bank-error.md')]);
      bensyneClient.getFileChunks.mockResolvedValue(Result.ko([new Error('boom')]));

      await service.resumeAll([aWatchSourceConfig({ id: 'test', path: '/tmp/test' })]);

      // No execute either way — but now through row exclusion, not a
      // defensive skip on a bank read that no longer happens.
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('a skip-row file is excluded by its row alone (health vocabulary never read)', async () => {
      enumerateOne('skip-row.md');
      fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([
        aFileTrackerRow('/tmp/test/skip-row.md', { skipReason: 'zero-chunks' }),
      ]);
      // Old code would have bank-verified this row (zero tracked memories ⇒
      // zeroChunks present path or untracked path). New: row = known, end.
      bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok(aFileChunksInfo({ status: 'present', chunks: [] })),
      );

      await service.resumeAll([aWatchSourceConfig({ id: 'test', path: '/tmp/test' })]);

      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
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
      // AC7 narrow exception: the `Resuming new file` string IS the operator
      // contract (replaces `Resuming untracked file`; bracket = queue position
      // within the NEW-FILES queue + queue size as denominator). ONE contract
      // test (T11 owns summary lines — untouched here).
      it('AC7 contract: logs `Resuming new file [i/totalFilesInQueue]: path="…"` with queue-local 1-based position (known files consume no position)', async () => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });

        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([
          mockDirent('known-a.md', false),
          mockDirent('fresh-a.md', false),
          mockDirent('known-b.md', false),
          mockDirent('fresh-b.md', false),
        ]);
        scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, [
          '/tmp/test/known-a.md',
          '/tmp/test/known-b.md',
        ]);

        await service.resumeAll([source]);

        // Capture ONLY queue-item log lines (the run header also starts with
        // "Resuming" — it is the entrypoint notice, not the pinned format).
        const resumeLogs = logger.info.mock.calls
          .map(call => (String(call[0]).startsWith('Resuming new file ') ? String(call[0]) : null))
          .filter((entry): entry is string => entry !== null);
        expect(resumeLogs).toEqual([
          'Resuming new file [1/2]: path="/tmp/test/fresh-a.md"',
          'Resuming new file [2/2]: path="/tmp/test/fresh-b.md"',
        ]);
        // The retired v1 string must not appear anywhere in the run.
        for (const call of logger.info.mock.calls) {
          expect(String(call[0])).not.toContain('Resuming untracked file');
          expect(String(call[0])).not.toContain('Resuming stale-tracker file');
        }
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
    // Spec §3.3 B14(a): for ttlDays-configured sources every QUEUED file is
    // activity-checked BEFORE any verify/ingest work; past-due files are
    // skipped with a single notice — behavior preserved unchanged by T10,
    // now operating on the new-files queue. ttlDays absent → gate not entered.
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
      // Pre-hard-deleted (forgotten) tracker row: after T10 the file is
      // simply un-known (queued); the activity gate must still skip it before
      // any execute/work happens.

      await service.resumeAll([source]);

      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalledWith(forgottenFile);
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).not.toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringMatching(/Skipping activity-expired file.*forgotten\.md/),
      );
    });

    it('processes a recent-mtime queued file normally — row age alone never triggers the skip', async () => {
      const source = aTtlSource();
      const activeFile = '/tmp/ttl-source/active.md';
      // Recent activity (1-day-old mtime) inside the 30-day window. T10
      // retarget (AC5 companion): the file is NEW (no row) — under the old
      // shape this test exercised the stale-tracker branch; the point stands
      // unchanged: mtime is the authoritative clock and a fresh activity lets
      // the queued file through to execute.
      stubFileMtimes(new Map([[activeFile, Date.now() - DAY_MS]]));
      fsMock.readdir.mockResolvedValue([mockDirent('active.md', false)]);

      await service.resumeAll([source]);

      // Retired-classifier guard (T10): the queued file reaches execute with
      // zero per-file tracker/bank reads.
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: activeFile, forceIngest: false }),
      );
      expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('Skipping activity-expired file'));
    });

    it('leaves the call set for a ttlDays-less source to the queue path only (gate not entered, no stat for the gate)', async () => {
      // Gate is defined solely by source.ttlDays; the builder omits it entirely.
      const source = aWatchSourceConfig({ id: 'plain-source', path: '/tmp/plain' });

      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('fresh.md', false)]);

      await service.resumeAll([source]);

      // T10 call set: row-set seam → execute (no per-file tracker lookup).
      expect(fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledWith('plain-source');
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: '/tmp/plain/fresh.md' }),
      );
      expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('Skipping activity-expired file'));

      // Negative guard: the gate branch must not run — the only stat is the
      // existing source-root stat, never the enumerated file.
      const statTargets = fsMock.stat.mock.calls.map(call => String(call[0]));
      expect(statTargets).not.toContain('/tmp/plain/fresh.md');
      expect(statTargets).toEqual(['/tmp/plain']);
    });

    it('summary files= counts the full NEW-FILES QUEUE including the activity-expired file (T11 / developer ruling 2026-11-02)', async () => {
      // Spec C8 literal: `resume finished: files=<new-files-queue size>` —
      // the queue IS the row-subtraction; an activity-expired file is part
      // of what resume took on and its gate-skip happens DOWNSTREAM of the
      // count, so `files=` stays the full queue size (3) while `ingested=`
      // counts only executed successes and `failed=` the ko outcomes. The
      // diverges from processed-attempts arithmetic exactly HERE (2 executes
      // vs 3 queued) — that is the whole point of this test.
      const source = aTtlSource();
      stubFileMtimes(
        new Map([
          ['/tmp/ttl-source/a-ok.md', Date.now()],
          ['/tmp/ttl-source/b-ko.md', Date.now()],
          ['/tmp/ttl-source/c-stale.md', Date.now() - 40 * DAY_MS],
        ]),
      );
      fsMock.readdir.mockResolvedValue([
        mockDirent('a-ok.md', false),
        mockDirent('b-ko.md', false),
        mockDirent('c-stale.md', false),
      ]);
      scriptOutcomesByPath(processFileUseCase.execute, {
        '/tmp/ttl-source/a-ok.md': 'ingest',
        '/tmp/ttl-source/b-ko.md': 'failure',
      });

      const summary = await service.resumeAll([source]);

      // The gate consumed the third file with zero execute work.
      expect(processFileUseCase.execute).toHaveBeenCalledTimes(2);
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringMatching(/Skipping activity-expired file.*c-stale\.md/),
      );
      // Emission: files=3 (full queue), ingested=1 (executed successes),
      // failed=1 (ko count).
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=3, ingested=1, failed=1']);
      // Returned DATA: same queue-size semantics (field names/shape frozen).
      expect(summary).toEqual({
        files: 3,
        gatedSkips: 0,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 1,
      });
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

    describe('resume new-files-only queue (T10 / DEC-A7 retarget)', () => {
      // v1's stale/untracked branch split no longer exists: the resume loop
      // has ONE execute shape. The stale-tracker repair moved to --recover
      // (DEC-A7 (a)) — its forceIngest:true lives in recover suites now.
      const queueFixture = (known: string[], queue: string[]) => {
        const source = aWatchSourceConfig({ id: 'test', path: '/tmp/test' });
        fsMock.stat.mockResolvedValue(mockDirStats());
        fsMock.readdir.mockResolvedValue([
          ...known.map(n => mockDirent(n, false)),
          ...queue.map(n => mockDirent(n, false)),
        ]);
        scriptKnownRows(
          fileTrackerRepository.findTrackedBySourceId,
          known.map(n => `/tmp/test/${n}`),
        );
        return source;
      };

      it('queued new file ⇒ forceIngest: false — explicitly passed, gate owns the file from there (AC3 retarget)', async () => {
        const source = queueFixture([], ['fresh.md']);

        await service.resumeAll([source]);

        const params = capturedParams();
        expect(params).toHaveLength(1);
        expect(params[0].filePath).toBe('/tmp/test/fresh.md');
        expect(params[0].forceIngest).toBe(false);
      });

      it('known files never reach execute regardless of row kind — queue owns exclusion, no bank read (no-change guard retarget)', async () => {
        const source = queueFixture(['known-normal.md', 'known-skip.md'], []);
        fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([
          aFileTrackerRow('/tmp/test/known-normal.md'),
          aFileTrackerRow('/tmp/test/known-skip.md', { skipReason: 'empty-content' }),
        ]);

        await service.resumeAll([source]);

        expect(processFileUseCase.execute).not.toHaveBeenCalled();
        expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
      });

      it('new files via autoPopulateSources (same internal path) ⇒ forceIngest: false too', async () => {
        const source = queueFixture([], ['fresh.md']);

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

    it('resume run: returned summary DATA equals the scripted outcome mix (T10 queue shape — no loop-level verified path exists)', async () => {
      // Scripted stream through the queue: real ingest (with memoryIds), a
      // hash-gate skip and a terminal skip (both legitimate execute()
      // outcomes for genuinely-new files under the faked seam), and a
      // known-row file that never reaches execute(). v1's loop-level
      // verified-healthy skip and stale-tracker forced re-ingest are GONE
      // (T10) — verifiedSkips stays 0 by construction.
      enumerate('a-fresh.md', 'b-gated.md', 'c-terminal.md', 'd-known.md');
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, [fileAt('d-known.md')]);
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('a-fresh.md')]: 'ingest',
        [fileAt('b-gated.md')]: 'gated-skip',
        [fileAt('c-terminal.md')]: 'terminal-skip',
      });

      const summary: BatchRunSummary = await service.resumeAll([c8Source()]);

      expect(summary).toEqual({
        files: 3, // queue size (ruling 2026-11-02): 3 new files; the known-row file never enters the queue (here queue==attempts)
        gatedSkips: 1,
        terminalSkipSkips: 1,
        verifiedSkips: 0, // classifier retired with the bank verification
        reIngested: 1,
      });
      // Retired-classifier guard on the same run.
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
    });

    it('resume summary accumulates across sources of one run (row-excluded files contribute nothing)', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('gated.md', false), mockDirent('ingest.md', false)])
        .mockResolvedValueOnce([mockDirent('known.md', false)]);
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, ['/tmp/c8-1/known.md']);
      scriptOutcomesByPath(processFileUseCase.execute, {
        '/tmp/c8-0/gated.md': 'gated-skip',
        '/tmp/c8-0/ingest.md': 'ingest',
      });

      const summary = await service.resumeAll([c8Source('c8-0', '/tmp/c8-0'), c8Source('c8-1', '/tmp/c8-1')]);

      expect(summary).toEqual({
        files: 2,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 1,
      });
    });

    it('cross-source run emits ONE aggregate resume line — run-scoped `failed=` and queue-sum `files=` across all sources (reviewer in-review pin: run-scoped tally semantics documented at ResumeRunTally but only ever asserted single-source until now)', async () => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir
        .mockResolvedValueOnce([mockDirent('line-ok.md', false), mockDirent('line-ko.md', false)])
        .mockResolvedValueOnce([mockDirent('new-in-1.md', false)]);
      scriptOutcomesByPath(processFileUseCase.execute, {
        '/tmp/c8-0/line-ok.md': 'ingest',
        '/tmp/c8-0/line-ko.md': 'failure',
        '/tmp/c8-1/new-in-1.md': 'ingest',
      });

      await service.resumeAll([c8Source('c8-0', '/tmp/c8-0'), c8Source('c8-1', '/tmp/c8-1')]);

      // ONE summary line for the WHOLE resumeAll run (not per source), with
      // the run-scoped counters: queue sizes 2+1=3, ingested 2, run ko count 1.
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=3, ingested=2, failed=1']);
    });

    it('single-source run (resumeSource) still composes and returns the summary', async () => {
      const sources = [c8Source('c8-0'), c8Source('keep-me')];
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue([mockDirent('gated.md', false)]);
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('gated.md')]: 'gated-skip' });

      const summary = await service.resumeSource('c8-0', sources);

      expect(summary).toEqual({
        files: 1,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 0,
      });
      // T11 split format (single-source resume path).
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=1, ingested=0, failed=0']);
    });

    it('auto-populate run (queue shape) composes and logs the summary (row-known file never counted)', async () => {
      // Spec §9 (amended): the flat C8 summary of the auto-populate pass IS
      // the acceptance check — the run path must carry the summary too.
      // T10: the known file is excluded by its row (verifiedSkips retired).
      // T11: the auto-populate pass shares the resume emission split — line
      // carries ONLY files/ingested/failed.
      enumerate('gated.md', 'known.md');
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, [fileAt('known.md')]);
      scriptOutcomesByPath(processFileUseCase.execute, { [fileAt('gated.md')]: 'gated-skip' });

      const summary = await service.autoPopulateSources([c8Source()]);

      expect(summary).toEqual({
        files: 1,
        gatedSkips: 1,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 0,
      });
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=1, ingested=0, failed=0']);
    });

    it('failed outcomes count as files only (never as a skip or a re-ingest)', async () => {
      enumerate('broken.md');
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

    it('resume counters (T11 / DEC-A7): scripted {queued 2: 1 ok, 1 ko} run emits the EXACT split resume line and correct summary DATA', async () => {
      // Counter machine as DATA; the emitted line is matched only as the exact
      // C8 split string (no `verified-skips` / other retired tokens anywhere
      // in it). The returned summary DATA keeps its field names/shape
      // unchanged (e2e + T12 assert on it) — the mode split is presentation
      // in logBatchSummary; `failed=` comes from an internal run counter only.
      enumerate('ok.md', 'ko.md');
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('ok.md')]: 'ingest',
        [fileAt('ko.md')]: 'failure',
      });

      const summary: BatchRunSummary = await service.resumeAll([c8Source()]);

      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=2, ingested=1, failed=1']);
      for (const line of summaryLinesFrom(logger.info)) {
        expect(line).not.toMatch(/verified-skips|gated-skips|terminal-skip-skips|re-ingested/);
      }

      expect(summary).toEqual({
        files: 2,
        gatedSkips: 0,
        terminalSkipSkips: 0,
        verifiedSkips: 0,
        reIngested: 1,
      });
      // The ko count feeds the resume LINE only — never the returned DATA.
      expect(Object.keys(summary).sort()).toEqual([
        'files',
        'gatedSkips',
        'reIngested',
        'terminalSkipSkips',
        'verifiedSkips',
      ]);

      // Same outcome mix through the force path (DEC-A7 keeps its full field
      // set): all five fields present, no split-format tokens (positive/negative
      // grep pair for the AC3 contract, new coverage — existing force
      // assertions above stay untouched).
      logger.info.mockClear();
      await service.forceReprocessAll([c8Source()]);
      expect(summaryLinesFrom(logger.info)).toEqual([
        'force-reprocess finished: files=2, gated-skips=0, terminal-skip-skips=0, verified-skips=0, re-ingested=1',
      ]);
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
      // files=0 is the healthy repeat-run signature (C8 amended) — T11 format.
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=0, ingested=0, failed=0']);

      logger.info.mockClear();
      const forceSummary = await service.forceReprocessAll([c8Source()]);

      expect(forceSummary).toEqual(aZeroRunSummary());
      expect(summaryLinesFrom(logger.info)).toEqual([
        'force-reprocess finished: files=0, gated-skips=0, terminal-skip-skips=0, verified-skips=0, re-ingested=0',
      ]);
    });

    it('emits exactly one resume summary line per completed run in the T11 split format (format contract: files/ingested/failed only)', async () => {
      // C8 (AMENDED 2026-11-02) / DEC-A7: resume and auto-populate paths emit
      // ONLY `resume finished: files=…, ingested=…, failed=…`. The
      // bank-verification `verified-skips` field retires from resume output
      // with the removed verification. ONE format contract test for this
      // string (narrow log-format exception); all other resume assertions here
      // are counter-behavior tests.
      enumerate('a-ok.md', 'b-ko.md');
      scriptOutcomesByPath(processFileUseCase.execute, {
        [fileAt('a-ok.md')]: 'ingest',
        [fileAt('b-ko.md')]: 'failure',
      });

      await service.resumeAll([c8Source()]);

      const lines = summaryLinesFrom(logger.info);
      expect(lines).toHaveLength(1);
      expect(lines[0]).toMatch(/^resume finished: files=\d+, ingested=\d+, failed=\d+$/);
      expect(lines[0]).toBe('resume finished: files=2, ingested=1, failed=1');
      // AC3 negative guard: retired v1 field tokens never appear in a resume line.
      for (const line of lines) {
        expect(line).not.toMatch(/verified-skips|gated-skips|terminal-skip-skips|re-ingested/);
      }
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
    const hbSource = () => aWatchSourceConfig({ id: 'hb-source', path: HB_ROOT });

    const enumerateHb = (count: number) => {
      fsMock.stat.mockResolvedValue(mockDirStats());
      fsMock.readdir.mockResolvedValue(
        Array.from({ length: count }, (_, i) => mockDirent(hbName(i + 1), false)),
      );
    };

    // v1 role residues (verified≡0 mod 50, stale≡7 mod 100) drove the
    // per-file getMemoryIds×bank classifiers — retired by T10/DEC-A7. The
    // T10 retarget keeps the outcome residues (failure≡3 mod 50, gated≡11
    // mod 25) on a pure queue stream: a `knownAt` residue marks row files
    // (never queued, zero per-file work); everything else is new → execute.
    // Deterministic and pairwise disjoint as before.
    const knownAt = (n: number) => n % 50 === 0; // FileTracker row present → excluded from the queue
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
      scriptKnownRows(
        fileTrackerRepository.findTrackedBySourceId,
        Array.from({ length: count }, (_, i) => i + 1)
          .filter(knownAt)
          .map(hbPath),
      );
      const script: Record<string, ScriptedOutcomeKind> = {};
      for (let n = 1; n <= count; n++) {
        if (knownAt(n)) continue; // row-known files never reach execute()
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

    const resumeHeartbeat = (
      processed: number,
      total: number,
      fields: [verified: number, gated: number, stale: number, untracked: number, failures: number],
    ) =>
      `resume progress: ${processed}/${total} processed (verified=${fields[0]}, gated=${fields[1]}, stale-repair=${fields[2]}, untracked=${fields[3]}, failures=${fields[4]})`;

    const forceHeartbeat = (processed: number, total: number, gated: number, failures: number) =>
      `force-reprocess progress: ${processed}/${total} processed (verified=0, gated=${gated}, stale-repair=0, untracked=0, failures=${failures})`;

    // Cumulative field values for the T10 queue stream at the k-th QUEUED
    // file. The `verified=` and `stale-repair=` classifiers were removed with
    // the bank verification (structurally 0 on the resume loop — the format
    // strings themselves are unchanged per Ad-Hoc F / T11), `untracked=` is
    // the queue's own branch (every file the loop processes is by definition
    // new-files-queue), gated/failures come from outcomes.
    const queuedIndexAt = (k: number): number => {
      let n = 0;
      while (n < 3000) {
        n += 1;
        if (!knownAt(n)) {
          k -= 1;
          if (k === 0) return n;
        }
      }
      throw new Error(`no ${k}th queued file within 3000`);
    };

    const fieldsAt = (k: number): [number, number, number, number, number] => {
      const lastN = queuedIndexAt(k);
      const gated = countUpTo(isGatedAt, lastN);
      const failures = countUpTo(isFailureAt, lastN);
      return [0, gated, 0, k, failures];
    };

    // Denominator shown in resume heartbeats = the NEW-FILES queue size.
    const queueSize = (count: number): number => {
      let k = 0;
      for (let n = 1; n <= count; n++) {
        if (!knownAt(n)) k += 1;
      }
      return k;
    };

    it('resumes of 250 files (row + outcome mix) emit heartbeats EXACTLY at queue positions 100 and 200 with correct cumulative fields (none at 50/150/250)', async () => {
      // T10 retarget: the denominator is the NEW-FILES QUEUE size (246 of the
      // 250 enumerated — n%50==0 carry rows), and heartbeats count QUEUED
      // files only: a row-known file consumes no processed index at all.
      scriptResumeRoles(250);

      await service.resumeAll([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([
        resumeHeartbeat(100, queueSize(250), fieldsAt(100)),
        resumeHeartbeat(200, queueSize(250), fieldsAt(200)),
      ]);
    });

    it('a run of 100 enumerated / 98 queued files emits NO heartbeat (below the queue threshold) and only the normal final summary (no duplicate)', async () => {
      scriptResumeRoles(100);

      await service.resumeAll([hbSource()]);

      // v1: 100 enumerated files were 100 processed → one 100/100 heartbeat.
      // T10: heartbeats count QUEUED files only; 98 queued < 100 → silent.
      // Row-excluded files consuming no processed index is exactly what
      // quiets steady-state loops (DEC-A7 / G5).
      expect(heartbeatLinesFrom(logger.info)).toEqual([]);
      // T11 split format: files=queue size (98 queued of the 100 enumerated
      // — queue==attempts here, numbers invariant under the ruling),
      // ingested=successful (92), failed=ko outcomes (n≡3 mod 50 within
      // 1..100 minus row hits → 2).
      expect(summaryLinesFrom(logger.info)).toEqual(['resume finished: files=98, ingested=92, failed=2']);
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

    it('resume progress line matches the contracted format exactly (format contract, resume prefix; T10: verified/stale-repair structurally 0)', async () => {
      // All-new queue (no rows): format string unchanged (Ad-Hoc F contract;
      // T11 owns the final-summary lines). The removed classifiers now read
      // 0 by construction — pinned here so a format drift can't sneak in.
      enumerateHb(130);

      await service.resumeAll([hbSource()]);

      const lines = heartbeatLinesFrom(logger.info);
      expect(lines).toEqual([
        'resume progress: 100/130 processed (verified=0, gated=0, stale-repair=0, untracked=100, failures=0)',
      ]);
      expect(lines[0]).toMatch(RESUME_HB_RE);
      expect(fileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(bensyneClient.getFileChunks).not.toHaveBeenCalled();
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

      // scriptResumeRoles(150) ⇒ rows at {50,100,150}: resume-prefix and
      // queue-size expectations both follow the queue (147), not enumeration.
      expect(heartbeatLinesFrom(logger.info)).toEqual([resumeHeartbeat(100, queueSize(150), fieldsAt(100))]);
    });

    it('field provenance (T10): row files contribute to no field; outcome files contribute only to their own; terminal-skip contributes to none; ko adds failures on top', async () => {
      // T10 retarget (v1's bank-verified-healthy provenance no longer
      // exists). Rows sit at n=50,100 → those two files are invisible to the
      // loop entirely (no field, no processed index). 98 queued files reach
      // execute (1 terminal-skip, 1 gated, 1 ko, 95 ingests). At the 100th
      // PROCESSED (none — 98 queued): no heartbeat fires at all; asserting
      // the zero-heartbeat + summary DATA instead: terminal-skip and ko
      // files add to files/failed only. A single-processed-index heartbeat
      // would carry untracked= its queue position — provenance unchanged in
      // kind, classifications removed.
      enumerateHb(100);
      scriptKnownRows(fileTrackerRepository.findTrackedBySourceId, [hbPath(50), hbPath(100)]);
      scriptOutcomesByPath(processFileUseCase.execute, {
        [hbPath(97)]: 'terminal-skip',
        [hbPath(98)]: 'gated-skip',
        [hbPath(99)]: 'failure',
      });

      const summary = await service.resumeAll([hbSource()]);

      expect(heartbeatLinesFrom(logger.info)).toEqual([]);
      // files counts every execute; gate/terminal hits from the outcomes;
      // verifiedSkips frozen at 0 (classifier gone); row files invisible.
      expect(summary).toEqual({
        files: 98,
        gatedSkips: 1,
        terminalSkipSkips: 1,
        verifiedSkips: 0,
        reIngested: 95,
      });
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
