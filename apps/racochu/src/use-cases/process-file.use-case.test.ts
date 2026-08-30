import * as fs from 'fs/promises';

import '@/utils/mastra-rag.test-utils';

import { DEFAULT_CONTENT_FILTER_OPTIONS } from '../application/content-classifier.service';
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
import { guardBase64Content } from '../utils/base64-guard';
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
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-old-1']);
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
      // ADD has no old memories — forgetByFile must never be called
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
    });
  });

  describe('forgetByFile stale-memory cleanup on CHANGE', () => {
    const filePath = '/path/to/file.md';
    const sourceId = 'test-source';
    const memoryBank = 'test-memoryBank';
    const fileContent = 'Updated content';
    const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
    const chunks = [aContentChunk({ text: 'updated chunk' })];

    const forgetFileSuccess = () =>
      Result.ok({ status: 'forgotten', file_id: 'mock-file-id', files_affected: 2 } as never);

    beforeEach(() => {
      (fs.readFile as jest.Mock).mockResolvedValue(fileContent);
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());
    });

    it('should return ok when memory IDs are empty and not call forgetByFile', async () => {
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue([]);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
    });

    it('should call forgetByFile with (filePath, memoryBank) before ingest and never call forget', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(forgetFileSuccess());
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      // forgetByFile must be called BEFORE re-ingestion (critical ordering: it
      // tombstones the file and would destroy newly-ingested memories otherwise)
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockBensyneClient.forgetByFile.mock.invocationCallOrder[0]).toBeLessThan(
        mockIngestChunkUseCase.execute.mock.invocationCallOrder[0],
      );
      // Per-memory forget must never be called on the change path
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should pass params.memoryBank to forgetByFile', async () => {
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);
      mockBensyneClient.forgetByFile.mockResolvedValue(forgetFileSuccess());
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank: 'custom-bank',
        sourceConfig: aSourceConfig({ id: sourceId, memoryBank: 'custom-bank' }),
      });

      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, 'custom-bank');
    });

    it('should ingest and return ok when forgetByFile returns Result.ko', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(Result.ko([new Error('MEMORY_BANK_NOT_SUPPORTED')]));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // forgetByFile failure is non-blocking — ingest proceeds, result stays ok
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      // Tracker cleanup still happens even when forgetByFile fails
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should call tracker.forgetMemories after ingest with all old IDs even when forgetByFile fails', async () => {
      const oldMemoryIds = ['mem-1', 'mem-2'];
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(oldMemoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(Result.ko([new Error('MEMORY_BANK_NOT_SUPPORTED')]));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      // Ingest happens AFTER forgetByFile (even on failure)
      expect(mockBensyneClient.forgetByFile.mock.invocationCallOrder[0]).toBeLessThan(
        mockIngestChunkUseCase.execute.mock.invocationCallOrder[0],
      );
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should ingest and return ok when forgetByFile throws', async () => {
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-1']);
      mockBensyneClient.forgetByFile.mockRejectedValue(new Error('MCP transport error'));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(result.isOk()).toBe(true);
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalled();
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

    it('should get old IDs, call forgetByFile before re-ingest, then forgetMemories on change', async () => {
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
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 2 }),
      );
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Verify the 4-step flow: get old IDs → forgetByFile → ingest → remove from tracker
      expect(mockFileMemoryTrackerService.getMemoryIds).toHaveBeenCalledWith(filePath);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should skip forgetByFile and tracker cleanup when no old memories exist on change', async () => {
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
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).not.toHaveBeenCalled();
    });

    it('should still call forgetByFile before an ingest failure (it runs first)', async () => {
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
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 1 }),
      );
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // forgetByFile runs BEFORE ingest, so an ingest failure does not undo it
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
    });

    it('should continue despite forgetByFile failure — ingest still runs, tracker still cleaned', async () => {
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
      mockBensyneClient.forgetByFile.mockResolvedValue(Result.ko([new Error('MEMORY_BANK_NOT_SUPPORTED')]));
      mockFileMemoryTrackerService.forgetMemories.mockResolvedValue(null);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Forget failure is non-blocking: ingest proceeds, result stays ok, tracker cleaned
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockChunkContentUseCase.execute).toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });

    it('should continue despite a tracker forgetMemories failure — returns ingest result', async () => {
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
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 1 }),
      );
      mockFileMemoryTrackerService.forgetMemories.mockRejectedValue(new Error('DB error'));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // forgetMemories failure is non-blocking: ingest result (ok) is returned
      expect(result.isOk()).toBe(true);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockIngestChunkUseCase.execute).toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.forgetMemories).toHaveBeenCalledWith(filePath, oldMemoryIds);
    });
  });

  describe('execute with DELETE event', () => {
    it('should get memoryIds, call forgetByFile, then deleteByFilePath on delete', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2', 'mem-3'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 1 } as never),
      );
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
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      // Per-memory forget should NOT be called
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
    });

    it('should be an idempotent no-op when no mappings found', async () => {
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
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
    });

    it('should return ok even when deleteByFilePath fails', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 1 } as never),
      );
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
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });
  });

  describe('execute with DELETE event — forgetByFile flow', () => {
    it('should call forgetByFile instead of per-memory forget on successful delete', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1', 'mem-2', 'mem-3'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(
        Result.ok({ status: 'forgotten', file_id: 'file-1', files_affected: 1 }),
      );
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
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledTimes(1);
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      // Per-memory forget should NOT be called
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      // Tracker cleanup should still occur
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });

    it('should log forgetByFile failure, continue tracker cleanup, and return ok (non-blocking)', async () => {
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'test-memoryBank';
      const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
      const memoryIds = ['mem-1'];

      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(memoryIds);
      mockBensyneClient.forgetByFile.mockResolvedValue(Result.ko([new Error('MCP transport error')]));
      mockFileMemoryTrackerService.deleteByFilePath.mockResolvedValue(undefined);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'delete',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      // Result should be ok (failure is non-blocking)
      expect(result.isOk()).toBe(true);
      // forgetByFile was attempted
      expect(mockBensyneClient.forgetByFile).toHaveBeenCalledWith(filePath, memoryBank);
      // Tracker cleanup still occurs despite forgetByFile failure
      expect(mockFileMemoryTrackerService.deleteByFilePath).toHaveBeenCalledWith(filePath);
    });

    it('should be an idempotent no-op when no memory mappings exist', async () => {
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
      // Early return — no bensyne call, no tracker cleanup
      expect(mockBensyneClient.forgetByFile).not.toHaveBeenCalled();
      expect(mockBensyneClient.forget).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
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

  describe('base64 blob guard wiring', () => {
    const filePath = '/path/to/base64-file.json';
    const sourceId = 'test-source';
    const memoryBank = 'test-memoryBank';
    const sourceConfig = aSourceConfig({ id: sourceId, memoryBank });
    const chunks = [aContentChunk()];

    beforeEach(() => {
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());
    });

    it('sanitizes a whole-file base64 blob (envelope) before chunking', async () => {
      const blob = `{"result":"${'YWFh'.repeat(50)}"}`;
      (fs.readFile as jest.Mock).mockResolvedValue(blob);

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      const expected = guardBase64Content(blob);
      // The guard must flag this as a blob.
      expect(expected.sanitized).toBe(true);
      // Chunking receives the placeholder, not the raw blob.
      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ content: expected.content }),
      );
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalledWith(
        expect.objectContaining({ content: blob }),
      );
    });

    it('sanitizes a whole-file pure base64 blob before chunking', async () => {
      const blob = 'YWFh'.repeat(60); // 240 chars, pure base64
      (fs.readFile as jest.Mock).mockResolvedValue(blob);

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ content: guardBase64Content(blob).content }),
      );
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalledWith(
        expect.objectContaining({ content: blob }),
      );
    });

    it('leaves non-blob file content unchanged when chunking', async () => {
      const normal = '# My Note\n\nThis is regular markdown content, not base64.';
      (fs.readFile as jest.Mock).mockResolvedValue(normal);

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ content: normal }),
      );
    });

    it('leaves short base64 (< 64 chars) unchanged when chunking', async () => {
      const shortB64 = 'aGVsbG8gd29ybGQ=';
      (fs.readFile as jest.Mock).mockResolvedValue(shortB64);

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig,
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ content: shortB64 }),
      );
    });
  });

  describe('content filter', () => {
    const filePath = '/path/to/dump.txt';
    const sourceId = 'test-source';
    const memoryBank = 'test-memoryBank';
    // git merge-tree dump excerpt — 3 of 11 lines match the machine-marker
    // patterns (27% > 5% default markerRatio), so the classifier flags it.
    const FILTERED_DUMP_CONTENT = [
      'added in remote',
      '  their  100644 57d0e502d5855bd14208313fa99a4cecac1faeee .vault/_Vault-Home.md',
      '@@ -0,0 +1,20 @@',
      '+---',
      '+type: index',
      '+title: "Vault Home"',
      '+createdAt: "2026-06-08T18:32:00Z"',
      '+updatedAt: "2026-06-10T20:00:00Z"',
      '+tags: []',
      '+',
      '+# Vault Home',
    ].join('\n');

    it('skips a filtered file entirely on ADD — no chunking, no ingest, no tracker row, empty outcome', async () => {
      (fs.readFile as jest.Mock).mockResolvedValue(FILTERED_DUMP_CONTENT);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig: aSourceConfig({ id: sourceId, memoryBank }),
      });

      expect(result.isOk()).toBe(true);
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(mockBensyneClient.remember).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.getMemoryIds).not.toHaveBeenCalled();
      expect(mockFileMemoryTrackerService.deleteByFilePath).not.toHaveBeenCalled();
    });

    it('skips a filtered file on CHANGE — no chunking, no ingest, no remember', async () => {
      (fs.readFile as jest.Mock).mockResolvedValue(FILTERED_DUMP_CONTENT);
      mockFileMemoryTrackerService.getMemoryIds.mockResolvedValue(['mem-old']);
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      const result = await useCase.execute({
        filePath,
        eventType: 'change',
        sourceId,
        memoryBank,
        sourceConfig: aSourceConfig({ id: sourceId, memoryBank }),
      });

      expect(result.isOk()).toBe(true);
      expect(mockChunkContentUseCase.execute).not.toHaveBeenCalled();
      expect(mockIngestChunkUseCase.execute).not.toHaveBeenCalled();
      expect(mockBensyneClient.remember).not.toHaveBeenCalled();
    });

    it('ingests filtered-looking content when contentFilter.enabled is false', async () => {
      (fs.readFile as jest.Mock).mockResolvedValue(FILTERED_DUMP_CONTENT);
      const chunks = [aContentChunk()];
      mockChunkContentUseCase.execute.mockResolvedValue(Result.ok(chunks));
      mockIngestChunkUseCase.execute.mockResolvedValue(Result.ok({ memoryIds: [] }));
      mockProcessingQueue.addToQueue.mockImplementation(task => task());

      await useCase.execute({
        filePath,
        eventType: 'add',
        sourceId,
        memoryBank,
        sourceConfig: aSourceConfig({
          id: sourceId,
          memoryBank,
          contentFilter: { ...DEFAULT_CONTENT_FILTER_OPTIONS, enabled: false },
        }),
      });

      expect(mockChunkContentUseCase.execute).toHaveBeenCalledWith(
        expect.objectContaining({ content: FILTERED_DUMP_CONTENT }),
      );
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
