import '@/utils/mastra-rag.test-utils';

import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { FileTracker } from '@/domain/file-tracker.aggregate';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { FileTrackerRepository } from '@/infrastructure/repositories/file-tracker.repository';
import { BensyneClient } from '@/infrastructure/services/bensyne-client.service';
import { aBensyneClientService } from '@/infrastructure/services/bensyne-client.test-utils';
import { FileHasherService } from '@/infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from '@/infrastructure/services/file-memory-tracker.service';
import { aFileMemoryTrackerService } from '@/infrastructure/services/file-memory-tracker.service.test-utils';
import { FileProcessingQueue } from '@/infrastructure/services/file-processing-queue.service';
import { aFileProcessingQueueService } from '@/infrastructure/services/file-processing-queue.test-utils';
import { HardwareIdDetectorService } from '@/infrastructure/services/hardware-id-detector.service';
import { Test, TestingModule } from '@nestjs/testing';
import * as fsPromises from 'fs/promises';
import { ChunkContentUseCase } from '../use-cases/chunk-content.use-case';
import { aChunkContentUseCase } from '../use-cases/chunk-content.use-case.test-utils';
import { IngestChunkUseCase } from '../use-cases/ingest-chunk.use-case';
import { aIngestChunkUseCase } from '../use-cases/ingest-chunk.use-case.test-utils';
import { ProcessFileUseCase } from '../use-cases/process-file.use-case';
import { aProcessFileUseCase } from '../use-cases/process-file.use-case.test-utils';
import { Result } from '../utils/result';
import { RecoverService } from './recover.service';

jest.mock('fs/promises');
const fsMock = fsPromises as jest.Mocked<typeof fsPromises>;

const CHUNK_HASH_0 = 'a'.repeat(64);
const CHUNK_HASH_1 = 'b'.repeat(64);

interface TestDeps {
  fileTrackerRepository: { findTrackedBySourceId: jest.Mock };
  fileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;
  processFileUseCase: ReturnType<typeof aProcessFileUseCase>;
  chunkContentUseCase: ReturnType<typeof aChunkContentUseCase>;
  ingestChunkUseCase: ReturnType<typeof aIngestChunkUseCase>;
  bensyneClient: ReturnType<typeof aBensyneClientService>;
  fileHasherService: { compute: jest.Mock };
  hardwareIdDetectorService: { getHardwareId: jest.Mock };
  processingQueue: ReturnType<typeof aFileProcessingQueueService> | FileProcessingQueue;
}

async function buildModule(overrides: Partial<TestDeps> = {}): Promise<{
  service: RecoverService;
  deps: TestDeps;
}> {
  const deps: TestDeps = {
    fileTrackerRepository: { findTrackedBySourceId: jest.fn().mockResolvedValue([]) },
    fileMemoryTrackerService: aFileMemoryTrackerService(),
    processFileUseCase: aProcessFileUseCase(),
    chunkContentUseCase: aChunkContentUseCase(),
    ingestChunkUseCase: aIngestChunkUseCase(),
    bensyneClient: aBensyneClientService(),
    fileHasherService: { compute: jest.fn().mockResolvedValue('current-hash') },
    hardwareIdDetectorService: { getHardwareId: jest.fn().mockResolvedValue('hw-id') },
    processingQueue: aFileProcessingQueueService(),
    ...overrides,
  };

  const module: TestingModule = await Test.createTestingModule({
    providers: [
      RecoverService,
      { provide: FileTrackerRepository, useValue: deps.fileTrackerRepository },
      { provide: FileMemoryTrackerService, useValue: deps.fileMemoryTrackerService },
      { provide: ProcessFileUseCase, useValue: deps.processFileUseCase },
      { provide: ChunkContentUseCase, useValue: deps.chunkContentUseCase },
      { provide: IngestChunkUseCase, useValue: deps.ingestChunkUseCase },
      { provide: BensyneClient, useValue: deps.bensyneClient },
      { provide: FileHasherService, useValue: deps.fileHasherService },
      { provide: HardwareIdDetectorService, useValue: deps.hardwareIdDetectorService },
      { provide: FileProcessingQueue, useValue: deps.processingQueue },
      { provide: BasePinoLogger, useValue: aLogger() },
    ],
  }).compile();

  return { service: module.get<RecoverService>(RecoverService), deps };
}

const FILE_PATH = '/tmp/source/file.md';

// Default tracker hash equals the default FileHasherService.compute result so the
// hash gate does not fire in comparison-path tests; the changed-file test overrides it.
function aTracker(overrides: { fileHash?: string | null; hardwareId?: string | null } = {}): FileTracker {
  return FileTracker.of({
    filePath: FILE_PATH,
    fileHash: overrides.fileHash === null ? undefined : (overrides.fileHash ?? 'current-hash'),
    hardwareId: overrides.hardwareId === null ? undefined : (overrides.hardwareId ?? 'tracked-hw'),
  }).getValue();
}

function aSource() {
  return aWatchSourceConfig({ id: 'source-1', path: '/tmp/source', memoryBank: 'bank-1' });
}

/** Two expected chunks (indexes 0 and 1) with stable chunkHashes. */
function expectedChunks(): ReturnType<typeof aBodyChunk>[] {
  return [
    aBodyChunk({
      chunkIndex: 0,
      totalChunks: 2,
      metadata: { filePath: FILE_PATH, chunkHash: CHUNK_HASH_0 },
    }),
    aBodyChunk({
      chunkIndex: 1,
      totalChunks: 2,
      metadata: { filePath: FILE_PATH, chunkHash: CHUNK_HASH_1 },
    }),
  ];
}

/** Same set returned by the enriched re-chunk pass (config as-is). */
function enrichedChunks(): ReturnType<typeof aBodyChunk>[] {
  return expectedChunks();
}

describe('RecoverService', () => {
  let deps: TestDeps;
  let service: RecoverService;

  beforeEach(async () => {
    jest.clearAllMocks();
    fsMock.access.mockReset();
    fsMock.readFile.mockReset();

    fsMock.access.mockResolvedValue(undefined);
    fsMock.readFile.mockResolvedValue('file content');

    ({ service, deps } = await buildModule());
  });

  describe('recoverAll / recoverSource iteration', () => {
    it('iterates DB-tracked files only — a filesystem file with no tracker row is never processed', async () => {
      // The repository reports zero tracked files even though the file exists on disk.
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([]);

      await service.recoverAll([aSource()]);

      expect(deps.fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledWith('source-1');
      expect(fsMock.access).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('recoverAll recovers every tracker returned for each source', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({
          status: 'present',
          chunks: [
            { chunkIndex: 0, contentHash: CHUNK_HASH_0, memoryStatus: 'present' },
            { chunkIndex: 1, contentHash: CHUNK_HASH_1, memoryStatus: 'present' },
          ],
        }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverAll([aSource()]);

      expect(deps.fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledTimes(1);
      expect(deps.bensyneClient.getFileChunks).toHaveBeenCalledTimes(1);
    });

    it('recoverSource filters trackers by sourceId and only processes that source', async () => {
      const source = aSource();
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({
          status: 'present',
          chunks: [
            { chunkIndex: 0, contentHash: CHUNK_HASH_0, memoryStatus: 'present' },
            { chunkIndex: 1, contentHash: CHUNK_HASH_1, memoryStatus: 'present' },
          ],
        }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverSource('source-1', [source]);

      expect(deps.fileTrackerRepository.findTrackedBySourceId).toHaveBeenCalledWith('source-1');
      expect(deps.bensyneClient.getFileChunks).toHaveBeenCalledTimes(1);
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('recoverSource does nothing when the source is not in the provided list', async () => {
      await service.recoverSource('missing', [aSource()]);

      expect(deps.fileTrackerRepository.findTrackedBySourceId).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });
  });

  describe('decision table', () => {
    it('skips a tracker row whose file is missing on disk — no exception, no submission', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      fsMock.access.mockRejectedValue(new Error('ENOENT'));

      await expect(service.recoverAll([aSource()])).resolves.not.toThrow();

      expect(deps.bensyneClient.getFileChunks).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('FILE_NOT_FOUND from getFileChunks triggers a full re-ingest with eventType "add"', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(Result.ok({ status: 'FILE_NOT_FOUND', chunks: [] }));

      await service.recoverAll([aSource()]);

      expect(deps.processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(deps.processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          filePath: FILE_PATH,
          eventType: 'add',
          sourceId: 'source-1',
          memoryBank: 'bank-1',
        }),
      );
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('a changed file (current fileHash differs from tracker, non-null) triggers a full re-ingest with eventType "change"', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([
        aTracker({ fileHash: 'old-tracked-hash' }),
      ]);
      deps.fileHasherService.compute.mockResolvedValue('current-hash');
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );

      await service.recoverAll([aSource()]);

      expect(deps.processFileUseCase.execute).toHaveBeenCalledTimes(1);
      expect(deps.processFileUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ filePath: FILE_PATH, eventType: 'change' }),
      );
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('a legacy null tracker fileHash skips the hash gate and proceeds to chunk-set comparison', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker({ fileHash: null })]);
      // Current hash differs from nothing — the gate must not fire.
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({
          status: 'present',
          chunks: [
            { chunkIndex: 0, contentHash: CHUNK_HASH_0, memoryStatus: 'present' },
            { chunkIndex: 1, contentHash: CHUNK_HASH_1, memoryStatus: 'present' },
          ],
        }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverAll([aSource()]);

      // No re-ingest — the flow reached the (healthy) chunk-set comparison.
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ skipEnrichment: true }),
      );
    });

    it('skips a healthy file (chunk sets match, all memoryStatus present) — zero ingest calls, expected set computed with skipEnrichment only', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({
          status: 'present',
          chunks: [
            { chunkIndex: 0, contentHash: CHUNK_HASH_0, memoryStatus: 'present' },
            { chunkIndex: 1, contentHash: CHUNK_HASH_1, memoryStatus: 'present' },
          ],
        }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverAll([aSource()]);

      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      // Verification runs exactly one cheap (skipEnrichment) chunk pass — no enriched re-chunk.
      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledTimes(1);
      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ skipEnrichment: true }),
      );
    });

    it('repairs a missing chunk index — only the repair-set chunk is submitted via IngestChunkUseCase with forceReembed and hashes', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute
        .mockResolvedValueOnce(Result.ok(expectedChunks())) // skipEnrichment verification pass
        .mockResolvedValueOnce(Result.ok(enrichedChunks())); // enriched repair pass

      await service.recoverAll([aSource()]);

      // The submit is enqueued through the queue (stub queue does not run tasks —
      // invoke the enqueued closure to assert what actually gets submitted).
      const queue = deps.processingQueue as jest.Mocked<ReturnType<typeof aFileProcessingQueueService>>;
      expect(queue.addToQueue).toHaveBeenCalledTimes(1);
      const task = queue.addToQueue.mock.calls[0][0] as () => Promise<void>;
      await task();

      expect(deps.ingestChunkUseCase.execute).toHaveBeenCalledTimes(1);
      const submitted = deps.ingestChunkUseCase.execute.mock.calls[0][0] as {
        chunks: { chunkIndex: number }[];
        forceReembed?: boolean;
        fileHash?: string;
        hardwareId?: string;
        metadata?: Record<string, string>;
      };
      expect(submitted.chunks).toHaveLength(1);
      expect(submitted.chunks[0].chunkIndex).toBe(1);
      expect(submitted.forceReembed).toBe(true);
      expect(submitted.fileHash).toBe('current-hash');
      expect(submitted.hardwareId).toBe('hw-id');
      expect(submitted.metadata).toEqual({ filePath: FILE_PATH });
    });

    it('repairs a chunk whose stored memoryStatus is "missing"', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({
          status: 'present',
          chunks: [
            { chunkIndex: 0, contentHash: CHUNK_HASH_0, memoryStatus: 'present' },
            { chunkIndex: 1, contentHash: CHUNK_HASH_1, memoryStatus: 'missing' },
          ],
        }),
      );
      deps.chunkContentUseCase.execute
        .mockResolvedValueOnce(Result.ok(expectedChunks()))
        .mockResolvedValueOnce(Result.ok(enrichedChunks()));

      await service.recoverAll([aSource()]);

      const queue = deps.processingQueue as jest.Mocked<ReturnType<typeof aFileProcessingQueueService>>;
      expect(queue.addToQueue).toHaveBeenCalledTimes(1);
      const task = queue.addToQueue.mock.calls[0][0] as () => Promise<void>;
      await task();

      expect(deps.ingestChunkUseCase.execute).toHaveBeenCalledTimes(1);
      const submitted = deps.ingestChunkUseCase.execute.mock.calls[0][0] as {
        chunks: { chunkIndex: number }[];
      };
      // Only the missing-memory chunk (index 1) is re-submitted; the healthy chunk 0 is not.
      expect(submitted.chunks.map(c => c.chunkIndex)).toEqual([1]);
    });

    it('runs the enriched re-chunk pass for the repair set (skipEnrichment absent) and keeps healthy chunks out of the submit', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute
        .mockResolvedValueOnce(Result.ok(expectedChunks()))
        .mockResolvedValueOnce(Result.ok(enrichedChunks()));

      await service.recoverAll([aSource()]);

      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledTimes(2);
      expect(deps.chunkContentUseCase.execute).toHaveBeenNthCalledWith(
        1,
        expect.objectContaining({ skipEnrichment: true }),
      );
      expect(deps.chunkContentUseCase.execute).toHaveBeenNthCalledWith(
        2,
        expect.not.objectContaining({ skipEnrichment: true }),
      );
    });
  });

  describe('queue serialization', () => {
    it('enqueues the repair submit through the real queue and never calls addToQueue from inside a running task', async () => {
      const realQueue = new FileProcessingQueue(aLogger());
      ({ service, deps } = await buildModule({
        processingQueue: realQueue,
        fileTrackerRepository: { findTrackedBySourceId: jest.fn().mockResolvedValue([aTracker()]) },
      }));
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute
        .mockResolvedValueOnce(Result.ok(expectedChunks()))
        .mockResolvedValueOnce(Result.ok(enrichedChunks()));

      // The repair submit runs INSIDE a queued task (inTaskStorage active): a nested
      // addToQueue there must throw the queue's deadlock error. If RecoverService ever
      // called addToQueue from within a queued task, this assertion fails.
      let nestedQueueError: unknown = null;
      deps.ingestChunkUseCase.execute.mockImplementation(async () => {
        try {
          await realQueue.addToQueue(async () => undefined);
        } catch (error) {
          nestedQueueError = error;
        }
        return Result.ok({ memoryIds: ['mem-1'] });
      });

      await service.recoverAll([aSource()]);
      await realQueue.waitForEmpty();

      expect(realQueue.isProcessing()).toBe(false);
      expect(realQueue.length).toBe(0);
      expect(nestedQueueError).toBeInstanceOf(Error);
      expect((nestedQueueError as Error).message).toMatch(/deadlocks/);
      expect(deps.ingestChunkUseCase.execute).toHaveBeenCalledTimes(1);
    });

    it('processes multiple repair files through the real queue without deadlocking', async () => {
      const realQueue = new FileProcessingQueue(aLogger());
      const trackers = [
        aTracker(),
        FileTracker.of({ filePath: '/tmp/source/other.md', fileHash: 'current-hash' }).getValue(),
      ];
      ({ service, deps } = await buildModule({
        processingQueue: realQueue,
        fileTrackerRepository: { findTrackedBySourceId: jest.fn().mockResolvedValue(trackers) },
      }));
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverAll([aSource()]);
      await realQueue.waitForEmpty();

      // Both files' repairs completed (a nested addToQueue would have eaten one).
      expect(deps.ingestChunkUseCase.execute).toHaveBeenCalledTimes(2);
      expect(realQueue.isProcessing()).toBe(false);
    });
  });

  describe('dry-run', () => {
    it('performs the same verification but submits nothing and reports the outcome', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ok(expectedChunks()));

      await service.recoverAll([aSource()], { dryRun: true });

      // Verification ran (getFileChunks + cheap expected-set chunking)…
      expect(deps.bensyneClient.getFileChunks).toHaveBeenCalledTimes(1);
      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ skipEnrichment: true }),
      );
      // …but nothing was submitted: no enriched re-chunk, no ingest, no re-ingest.
      expect(deps.chunkContentUseCase.execute).toHaveBeenCalledTimes(1);
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
      expect(deps.processingQueue.addToQueue).not.toHaveBeenCalled();
    });
  });

  describe('error paths', () => {
    it('does not submit when the expected chunk set cannot be computed', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(
        Result.ok({ status: 'present', chunks: [aStoredPresent(0)] }),
      );
      deps.chunkContentUseCase.execute.mockResolvedValue(Result.ko([new Error('chunking failed')]));

      await expect(service.recoverAll([aSource()])).resolves.not.toThrow();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
    });

    it('does not submit when getFileChunks fails at the transport level', async () => {
      deps.fileTrackerRepository.findTrackedBySourceId.mockResolvedValue([aTracker()]);
      deps.bensyneClient.getFileChunks.mockResolvedValue(Result.ko([new Error('MCP down')]));

      await expect(service.recoverAll([aSource()])).resolves.not.toThrow();
      expect(deps.ingestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(deps.processFileUseCase.execute).not.toHaveBeenCalled();
    });
  });
});

/** Typed stored-chunk helper: a present chunk at the given index. */
function aStoredPresent(chunkIndex: number): {
  chunkIndex: number;
  contentHash: string;
  memoryId?: string;
  memoryStatus: 'present' | 'missing';
} {
  return {
    chunkIndex,
    contentHash: chunkIndex === 0 ? CHUNK_HASH_0 : CHUNK_HASH_1,
    memoryId: `mem-${chunkIndex}`,
    memoryStatus: 'present',
  };
}
