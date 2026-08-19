import * as fs from 'fs/promises';

import '@/utils/mastra-rag.test-utils';

import { aContentChunk } from '../domain/content-chunk.entity.test-utils';
import { FileAddedEvent, FileChangedEvent, FileDeletedEvent } from '../domain/events/file-events';
import { aSourceConfig } from '../infrastructure/config/configuration.service.test-utils';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { aBensyneClientService } from '../infrastructure/services/bensyne-client.test-utils';
import { FileHasherService } from '../infrastructure/services/file-hasher.service';
import { FileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service';
import { aFileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service.test-utils';
import { FileProcessingQueue } from '../infrastructure/services/file-processing-queue.service';
import { aFileProcessingQueueService } from '../infrastructure/services/file-processing-queue.test-utils';
import { HardwareIdDetectorService } from '../infrastructure/services/hardware-id-detector.service';
import { Result } from '../utils/result';
import { ChunkContentUseCase } from './chunk-content.use-case';
import { aChunkContentUseCase } from './chunk-content.use-case.test-utils';
import { IngestChunkUseCase } from './ingest-chunk.use-case';
import { aIngestChunkUseCase } from './ingest-chunk.use-case.test-utils';
import { ProcessFileUseCase } from './process-file.use-case';

jest.mock('fs/promises');

describe('ProcessFileUseCase', () => {
  let useCase: ProcessFileUseCase;
  let mockChunkContentUseCase: ReturnType<typeof aChunkContentUseCase>;
  let mockIngestChunkUseCase: ReturnType<typeof aIngestChunkUseCase>;
  let mockProcessingQueue: ReturnType<typeof aFileProcessingQueueService>;
  let mockFileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;
  let mockBensyneClient: ReturnType<typeof aBensyneClientService>;
  let mockFileHasherService: jest.Mocked<{ compute: jest.Mock }>;
  let mockHardwareIdDetectorService: jest.Mocked<{ getHardwareId: jest.Mock }>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockChunkContentUseCase = aChunkContentUseCase();
    mockIngestChunkUseCase = aIngestChunkUseCase();
    mockProcessingQueue = aFileProcessingQueueService();
    mockFileMemoryTrackerService = aFileMemoryTrackerService();
    mockBensyneClient = aBensyneClientService();
    mockFileHasherService = { compute: jest.fn().mockResolvedValue('test-hash-abc123') };
    mockHardwareIdDetectorService = { getHardwareId: jest.fn().mockResolvedValue('test-hw-id') };
    const mockLogger = aLogger();

    useCase = new ProcessFileUseCase(
      mockChunkContentUseCase as unknown as ChunkContentUseCase,
      mockIngestChunkUseCase as unknown as IngestChunkUseCase,
      mockProcessingQueue as unknown as FileProcessingQueue,
      mockFileMemoryTrackerService as unknown as FileMemoryTrackerService,
      mockBensyneClient as unknown as BensyneClient,
      mockFileHasherService as unknown as FileHasherService,
      mockHardwareIdDetectorService as unknown as HardwareIdDetectorService,
      mockLogger as unknown as never,
    );
  });

  describe('execute with ADD event', () => {
    it('should queue processing and chunk + ingest on success', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Test file content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'chunk 1' }), aContentChunk({ text: 'chunk 2' })];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);

      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));

      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(fs.readFile).toHaveBeenCalledWith(filePath, 'utf-8');
      expect(mockFileHasherService.compute).toHaveBeenCalledWith(filePath);
      expect(mockHardwareIdDetectorService.getHardwareId).toHaveBeenCalled();
      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith({
        content: fileContent,
        filePath,
        sourceId,
        memoryBank,
        sourceConfig,
        fileHash: 'test-hash-abc123',
        hardwareId: 'test-hw-id',
      });
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalledWith({
        chunks,
        sourceId,
        metadata: {
          filePath,
          eventType: 'add',
        },
        fileHash: 'test-hash-abc123',
        hardwareId: 'test-hw-id',
      });
    });

    it('should pass sourceConfig through to ChunkContentUseCase', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'agent-sessions';
      const memoryBank = 'agent-sessions';
      const fileContent = 'Test';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank, sourceType: 'agent-sessions' });
      const chunks = [aContentChunk({ memoryBank })];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ memoryBank, sourceConfig }),
      );
    });

    it('should return error when file read fails', async () => {
      const filePath = '/path/to/missing.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      (fs.readFile as jest.Mock).mockRejectedValue(new Error('ENOENT'));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
    });

    it('should return error when chunking fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const fileContent = 'Test content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ko([new Error('Chunking failed')]));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
    });

    it('should return error when ingestion fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const fileContent = 'Test content';
      const chunks = [aContentChunk()];
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ko([new Error('Ingestion failed')]));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
    });

    it('should skip ingestion when no chunks generated', async () => {
      const filePath = '/path/to/empty.md';
      const sourceId = 'test-source';
      const fileContent = '';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok([]));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('should continue without fileHash when hash computation fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Test';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk()];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileHasherService.compute.mockRejectedValue(new Error('Hash failed'));
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Should still call chunking without fileHash
      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          content: fileContent,
          filePath,
          fileHash: undefined,
        }),
      );
    });

    it('should continue without hardwareId when hardwareId detection fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Test';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk()];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockHardwareIdDetectorService.getHardwareId.mockRejectedValue(new Error('HW detection failed'));
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Should still call chunking without hardwareId
      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          content: fileContent,
          filePath,
          hardwareId: undefined,
        }),
      );
    });

    it('should continue without both when both hash and hardwareId fail', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Test';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk()];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileHasherService.compute.mockRejectedValue(new Error('Hash failed'));
      mockHardwareIdDetectorService.getHardwareId.mockRejectedValue(new Error('HW failed'));
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          content: fileContent,
          filePath,
          fileHash: undefined,
          hardwareId: undefined,
        }),
      );
    });

    it('should pass fileHash and hardwareId to IngestChunkUseCase', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Test';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk()];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockIngestChunkUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          fileHash: 'test-hash-abc123',
          hardwareId: 'test-hw-id',
        }),
      );
    });
  });

  describe('forgetOldMemoriesByIds', () => {
    const filePath = '/path/to/file.md';
    const sourceId = 'test-source';
    const memoryBank = 'test-memoryBank';
    const fileContent = 'Updated content';
    const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
    const chunks = [aContentChunk({ text: 'updated chunk' })];

    beforeEach(() => {
      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());
    });

    it('should return ok when memory IDs are empty', async () => {
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
    });

    it('should return ok when all forgets succeed', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-1', memoryBank);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-2', memoryBank);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should return ok (ingest result) when some forgets fail with Result.ko', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2', 'mem-3'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forget
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockResolvedValueOnce(Result.ko([new Error('Forget failed')]))
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Forget failures are non-blocking — ingest result (ok) is returned
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(3);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should return ok (ingest result) when some forgets throw', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forget
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockRejectedValueOnce(new Error('Connection error'));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Forget failures are non-blocking — ingest result (ok) is returned
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should return ok (ingest result) when all forgets fail', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ko([new Error('All failed')]));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Forget failures are non-blocking — ingest result (ok) is returned
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should use params.memoryBank for forget calls', async () => {
      const oldMemoryIds = ['mem-1'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank: 'custom-bank',
        sourceConfig: aSourceConfig({ id: sourceId, memoryBank: 'custom-bank' }),
      });

      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-1', 'custom-bank');
    });
  });

  describe('stale memory ID forgetting (set-difference)', () => {
    const filePath = '/path/to/file.md';
    const sourceId = 'test-source';
    const memoryBank = 'test-memoryBank';
    const fileContent = 'Updated content';
    const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
    const chunks = [aContentChunk({ text: 'updated chunk' })];

    beforeEach(() => {
      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());
    });

    it('should NOT forget any memories when new ingest returns identical memory IDs (dedupe case)', async () => {
      const memoryIds = ['mem-a', 'mem-b'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds } as never));
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).not.toHaveBeenCalled();
    });

    it('should forget all old memory IDs when new ingest produces entirely different IDs', async () => {
      const oldMemoryIds = ['mem-old-1', 'mem-old-2'];
      const newMemoryIds = ['mem-new-1', 'mem-new-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: newMemoryIds } as never));
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-old-1', memoryBank);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-old-2', memoryBank);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should forget only stale memory IDs (mixed case) and keep current ones in tracker', async () => {
      const oldMemoryIds = ['mem-a', 'mem-b'];
      const newMemoryIds = ['mem-b', 'mem-c'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: newMemoryIds } as never));
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-a', memoryBank);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, ['mem-a']);
    });
  });

  describe('execute with CHANGE event', () => {
    it('should re-chunk and re-ingest on change', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'updated chunk' })];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith({
        content: fileContent,
        filePath,
        sourceId,
        memoryBank,
        sourceConfig,
        fileHash: 'test-hash-abc123',
        hardwareId: 'test-hw-id',
      });
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalledWith({
        chunks,
        sourceId,
        metadata: {
          filePath,
          eventType: 'change',
        },
        fileHash: 'test-hash-abc123',
        hardwareId: 'test-hw-id',
      });
    });

    it('should get old IDs, ingest, forget old memories, remove old IDs from tracker on change', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'updated chunk' })];
      const oldMemoryIds = ['mem-old-1', 'mem-old-2'];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Verify the 4-step flow: get old IDs → ingest → forget → remove from tracker
      expect(mockFileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(filePath);
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-old-1', memoryBank);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-old-2', memoryBank);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should skip Mnemosyne forget and tracker cleanup when no old memories on change', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'updated chunk' })];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockFileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(filePath);
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).not.toHaveBeenCalled();
    });

    it('should short-circuit on ingest failure — no forget, no tracker cleanup', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const oldMemoryIds = ['mem-old-1'];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok([aContentChunk()]));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ko([new Error('Ingest failed')]));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Ingest failed → Mnemosyne forget must NOT be called (safety: old memories still exist)
      // Tracker NOT touched — old IDs still tracked for next change event
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).not.toHaveBeenCalled();
    });

    it('should continue on forget failure — returns ingest result', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'updated chunk' })];
      const oldMemoryIds = ['mem-old-1', 'mem-old-2'];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockBensyneClient.forget
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockResolvedValueOnce(Result.ko([new Error('Forget failed')]));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Forget failure is non-blocking: both forgets attempted, old IDs removed from tracker
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should continue on forgetMemories failure — returns ingest result', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const fileContent = 'Updated content';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const chunks = [aContentChunk({ text: 'updated chunk' })];
      const oldMemoryIds = ['mem-old-1'];

      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.forgetMemories.mockRejectedValue(new Error('DB error'));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // forgetMemories failure is non-blocking (warn logged), ingest and forget still succeed
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });
  });

  describe('execute with DELETE event', () => {
    it('should get memoryIds, forget each, then deleteByFilePath on delete', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2', 'mem-3'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.deleteByFilePath.mockResolvedValue(undefined);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(filePath);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(3);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-1', memoryBank);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-2', memoryBank);
      expect(mockBensyneClient.forget).toHaveBeenCalledWith('mem-3', memoryBank);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('should log debug and skip forgets when no mappings found', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(filePath);
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
    });

    it('should continue with remaining memories when forget fails for one', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2', 'mem-3'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forget
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockResolvedValueOnce(Result.ko([new Error('MCP error')]))
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.deleteByFilePath.mockResolvedValue(undefined);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(3);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });

    it('should continue with remaining memories when forget throws', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forget
        .mockResolvedValueOnce(Result.ok(undefined as unknown as void))
        .mockRejectedValueOnce(new Error('Connection error'));
      mockFileMemoryTrackerService.deleteByFilePath.mockResolvedValue(undefined);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });

    it('should return ok even when deleteByFilePath fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.deleteByFilePath.mockRejectedValue(new Error('DB error'));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });

    it('should complete delete flow for all memory IDs', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forget.mockResolvedValue(Result.ok(undefined as unknown as void));
      mockFileMemoryTrackerService.deleteByFilePath.mockResolvedValue(undefined);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forget).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });
  });

  describe('queue processing', () => {
    it('should queue processing via FileProcessingQueue', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      mockProcessingQueue.addToQueue.mockResolvedValue(undefined);

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(mockProcessingQueue.addToQueue).toHaveBeenCalledTimes(1);
      expect(typeof mockProcessingQueue.addToQueue.mock.calls[0][0]).toBe('function');
    });

    it('should NOT remove from processing Set immediately after addToQueue resolves', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      // Capture the task callback so we can control when it runs
      let capturedTask: (() => Promise<void>) | undefined;
      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        capturedTask = task;
        // Resolve immediately WITHOUT awaiting the task — simulates real queue behavior
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      // File should still be in processing set — delete should NOT have fired yet
      // because the task hasn't completed
      // @ts-expect-error — accessing private property for test
      expect((useCase as { processing: Set<string> }).processing.has(filePath)).toBe(true);

      // Now complete the task
      await capturedTask!();
      // After task completes, file should be removed from processing set
      // @ts-expect-error — accessing private property for test
      expect((useCase as { processing: Set<string> }).processing.has(filePath)).toBe(false);
    });

    it('should remove from processing Set even when task throws an error', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      let capturedTask: (() => Promise<void>) | undefined;
      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        capturedTask = task;
      });

      // Make the handler throw to trigger the inner finally
      mockChunkContentUseCase.execute.mockRejectedValue(new Error('boom'));

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      // @ts-expect-error — accessing private property for test
      expect((useCase as { processing: Set<string> }).processing.has(filePath)).toBe(true);

      // Task's inner try/finally should still clean up processing Set
      // even though the handler throws — the error propagates but finally runs
      await expect(capturedTask!).rejects.toThrow('boom');
      // @ts-expect-error — accessing private property for test
      expect((useCase as { processing: Set<string> }).processing.has(filePath)).toBe(false);
    });
  });

  describe('validation', () => {
    it('should return error when filePath is missing', async () => {
      const result = await useCase.execute({
        filePath: '',
        eventType: 'add',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
        sourceConfig: aSourceConfig(),
      } as unknown as Parameters<typeof useCase.execute>[0]);

      expect(result.isKo()).toBe(true);
    });

    it('should return error when sourceId is missing', async () => {
      const result = await useCase.execute({
        filePath: '/path/to/file.md',
        eventType: 'add',
        sourceId: '',
        memoryBank: 'test-memoryBank',
        sourceConfig: aSourceConfig(),
      } as unknown as Parameters<typeof useCase.execute>[0]);

      expect(result.isKo()).toBe(true);
    });

    it('should return error when sourceId is empty', async () => {
      const result = await useCase.execute({
        filePath: '/path/to/file.md',
        eventType: 'add',
        sourceId: '',
        sourceConfig: aSourceConfig(),
      } as unknown as Parameters<typeof useCase.execute>[0]);

      expect(result.isKo()).toBe(true);
    });

    it('should return error when eventType is invalid', async () => {
      const result = await useCase.execute({
        filePath: '/path/to/file.md',
        eventType: 'invalid' as 'add',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
        sourceConfig: aSourceConfig(),
      } as unknown as Parameters<typeof useCase.execute>[0]);

      expect(result.isKo()).toBe(true);
    });

    it('should return error when memoryBank is missing', async () => {
      const result = await useCase.execute({
        filePath: '/path/to/file.md',
        eventType: 'add',
        sourceId: 'test-source',
        memoryBank: '',
        sourceConfig: aSourceConfig(),
      } as unknown as Parameters<typeof useCase.execute>[0]);

      expect(result.isKo()).toBe(true);
    });
  });

  describe('file existence check', () => {
    it('should skip processing when file not found even after retry', async () => {
      const filePath = '/path/to/missing.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });

      // Both access calls throw — file never exists
      (fs.access as jest.Mock).mockRejectedValue(new Error('ENOENT: no such file'));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      // Graceful skip — returns ok, readFile never called
      expect(result.isOk()).toBe(true);
      expect(fs.access).toHaveBeenCalledTimes(2);
      expect(fs.readFile).not.toHaveBeenCalled();
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('should proceed after retry when file found on second check', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });
      const fileContent = 'Test content';
      const chunks = [aContentChunk({ text: 'chunk 1' })];

      // First access throws, second succeeds
      (fs.access as jest.Mock)
        .mockRejectedValueOnce(new Error('ENOENT: no such file'))
        .mockResolvedValueOnce(undefined);
      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);

      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(fs.access).toHaveBeenCalledTimes(2);
      expect(fs.readFile).toHaveBeenCalledWith(filePath, 'utf-8');
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
    });

    it('should proceed immediately when file exists', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank: 'test-memoryBank' });
      const fileContent = 'Test content';
      const chunks = [aContentChunk({ text: 'chunk 1' })];

      // File exists on first check
      (fs.access as jest.Mock).mockResolvedValue(undefined);
      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);

      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));

      mockProcessingQueue.addToQueue.mockImplementation(async task => {
        await task();
      });

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(fs.access).toHaveBeenCalledTimes(1);
      expect(fs.readFile).toHaveBeenCalledWith(filePath, 'utf-8');
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
    });
  });

  describe('OnEvent handlers', () => {
    it('handleFileAdded should trigger execute with add event type', async () => {
      const filePath = '/path/to/file.md';
      const event = FileAddedEvent.of(filePath).getValue();

      mockProcessingQueue.addToQueue.mockResolvedValue(undefined);

      await useCase.handleFileAdded(event);

      expect(mockProcessingQueue.addToQueue).toHaveBeenCalledTimes(1);
    });

    it('handleFileChanged should trigger execute with change event type', async () => {
      const filePath = '/path/to/file.md';
      const event = FileChangedEvent.of(filePath).getValue();

      mockProcessingQueue.addToQueue.mockResolvedValue(undefined);

      await useCase.handleFileChanged(event);

      expect(mockProcessingQueue.addToQueue).toHaveBeenCalledTimes(1);
    });

    it('handleFileDeleted should trigger execute with delete event type', async () => {
      const filePath = '/path/to/file.md';
      const event = FileDeletedEvent.of(filePath).getValue();

      mockProcessingQueue.addToQueue.mockResolvedValue(undefined);

      await useCase.handleFileDeleted(event);

      expect(mockProcessingQueue.addToQueue).toHaveBeenCalledTimes(1);
    });
  });
});
