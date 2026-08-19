import { ContentChunk } from '../domain/content-chunk.entity';
import { aContentChunk } from '../domain/content-chunk.entity.test-utils';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { aBensyneClientService } from '../infrastructure/services/bensyne-client.test-utils';
import { aFileMemoryTrackerService } from '../infrastructure/services/file-memory-tracker.service.test-utils';
import { Result } from '../utils/result';
import { IngestChunkUseCase } from './ingest-chunk.use-case';

// Mock BensyneClient module to avoid chokidar ESM import chain
jest.mock('../infrastructure/services/bensyne-client.service', () => ({
  BensyneClient: class BensyneClientMock {},
}));

// Mock FileMemoryTrackerService
jest.mock('../infrastructure/services/file-memory-tracker.service', () => ({
  FileMemoryTrackerService: class FileMemoryTrackerServiceMock {},
}));

describe('IngestChunkUseCase', () => {
  let useCase: IngestChunkUseCase;
  let mockBensyneClientService: ReturnType<typeof aBensyneClientService>;
  let mockFileMemoryTrackerService: ReturnType<typeof aFileMemoryTrackerService>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockBensyneClientService = aBensyneClientService();
    mockFileMemoryTrackerService = aFileMemoryTrackerService();
    const mockLogger = aLogger();

    useCase = new IngestChunkUseCase(
      mockBensyneClientService as never,
      mockFileMemoryTrackerService as never,
      mockLogger as never,
    );
  });

  describe('execute', () => {
    it('should ingest all valid chunks via BensyneClient.remember()', async () => {
      const chunks: ContentChunk[] = [aContentChunk({ chunkIndex: 0 }), aContentChunk({ chunkIndex: 1 })];
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-1', status: 'stored' }),
      );

      const result = await useCase.execute({ chunks, sourceId: 'test-source' });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClientService.remember).toHaveBeenCalledTimes(2);
      expect(mockBensyneClientService.remember).toHaveBeenCalledWith(chunks[0]);
      expect(mockBensyneClientService.remember).toHaveBeenCalledWith(chunks[1]);
    });

    it('should return ok when chunks array is empty', async () => {
      const result = await useCase.execute({ chunks: [], sourceId: 'test-source' });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClientService.remember).not.toHaveBeenCalled();
    });

    it('should handle partial failures without stopping all chunks', async () => {
      const chunk1 = aContentChunk({ chunkIndex: 0 });
      const chunk2 = aContentChunk({ chunkIndex: 1 });
      const chunk3 = aContentChunk({ chunkIndex: 2 });

      mockBensyneClientService.remember
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-1', status: 'stored' }))
        .mockResolvedValueOnce(Result.ko([new Error('MCP error')]))
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-3', status: 'stored' }));

      const result = await useCase.execute({
        chunks: [chunk1, chunk2, chunk3],
        sourceId: 'test-source',
      });

      expect(result.isOk()).toBe(true);
      expect(mockBensyneClientService.remember).toHaveBeenCalledTimes(3);
    });

    it('should return error when all chunks fail', async () => {
      const chunks: ContentChunk[] = [aContentChunk({ chunkIndex: 0 }), aContentChunk({ chunkIndex: 1 })];
      mockBensyneClientService.remember.mockResolvedValue(Result.ko([new Error('Connection refused')]));

      const result = await useCase.execute({ chunks, sourceId: 'test-source' });

      expect(result.isKo()).toBe(true);
      const error = result.getErrors()[0];
      expect(error.message).toContain('Failed to ingest all 2 chunks');
    });

    it('should handle BensyneClient.remember throwing an exception', async () => {
      const chunk = aContentChunk({ chunkIndex: 0 });
      mockBensyneClientService.remember.mockRejectedValue(new Error('Network timeout'));

      const result = await useCase.execute({ chunks: [chunk], sourceId: 'test-source' });

      expect(result.isKo()).toBe(true);
    });

    it('should return error when params are invalid', async () => {
      const result = await useCase.execute({ chunks: [], sourceId: '' });

      expect(result.isKo()).toBe(true);
    });
  });

  describe('enhanced chunk fields', () => {
    it('should pass enhanced chunk with memoryBank to BensyneClient.remember()', async () => {
      const enhancedChunk = aContentChunk({
        memoryBank: 'agent-sessions',
        importance: 0.85,
        tags: ['meeting-notes', 'architecture'],
      });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-1', status: 'stored' }),
      );

      await useCase.execute({ chunks: [enhancedChunk], sourceId: 'test-source' });

      const passedChunk = mockBensyneClientService.remember.mock.calls[0][0];
      expect(passedChunk.memoryBank).toBe('agent-sessions');
      expect(passedChunk.importance).toBe(0.85);
      expect(passedChunk.tags).toEqual(['meeting-notes', 'architecture']);
    });

    it('should pass enhanced chunk with importance to BensyneClient.remember()', async () => {
      const enhancedChunk = aContentChunk({ importance: 0.95 });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-1', status: 'stored' }),
      );

      await useCase.execute({ chunks: [enhancedChunk], sourceId: 'test-source' });

      const passedChunk = mockBensyneClientService.remember.mock.calls[0][0];
      expect(passedChunk.importance).toBe(0.95);
    });

    it('should pass enhanced chunk with tags to BensyneClient.remember()', async () => {
      const enhancedChunk = aContentChunk({ tags: ['typescript', 'api', 'critical'] });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-1', status: 'stored' }),
      );

      await useCase.execute({ chunks: [enhancedChunk], sourceId: 'test-source' });

      const passedChunk = mockBensyneClientService.remember.mock.calls[0][0];
      expect(passedChunk.tags).toEqual(['typescript', 'api', 'critical']);
    });

    it('should ingest multiple enhanced chunks preserving their fields', async () => {
      const chunk1 = aContentChunk({ memoryBank: 'ns1', importance: 0.7, tags: ['a'] });
      const chunk2 = aContentChunk({ memoryBank: 'ns2', importance: 0.9, tags: ['b', 'c'] });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-1', status: 'stored' }),
      );

      await useCase.execute({ chunks: [chunk1, chunk2], sourceId: 'test-source' });

      expect(mockBensyneClientService.remember).toHaveBeenCalledTimes(2);
      expect(mockBensyneClientService.remember.mock.calls[0][0].memoryBank).toBe('ns1');
      expect(mockBensyneClientService.remember.mock.calls[1][0].memoryBank).toBe('ns2');
    });
  });

  describe('memory IDs exposure', () => {
    it('should return ingested memory IDs in the result', async () => {
      const chunks = [aContentChunk({ chunkIndex: 0 }), aContentChunk({ chunkIndex: 1 })];
      mockBensyneClientService.remember
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-1', status: 'stored' }))
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-2', status: 'stored' }));
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks,
        sourceId: 'test-source',
        metadata: { filePath: '/test/file.md' },
      });

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ memoryIds: ['mem-1', 'mem-2'] });
    });

    it('should return only memory IDs from successful ingestions', async () => {
      const chunks = [
        aContentChunk({ chunkIndex: 0 }),
        aContentChunk({ chunkIndex: 1 }),
        aContentChunk({ chunkIndex: 2 }),
      ];
      mockBensyneClientService.remember
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-1', status: 'stored' }))
        .mockResolvedValueOnce(Result.ko([new Error('Failed')]))
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-3', status: 'stored' }));
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks,
        sourceId: 'test-source',
        metadata: { filePath: '/test/file.md' },
      });

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ memoryIds: ['mem-1', 'mem-3'] });
    });

    it('should return empty memoryIds array when no chunks to ingest', async () => {
      const result = await useCase.execute({
        chunks: [],
        sourceId: 'test-source',
      });

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual({ memoryIds: [] });
    });
  });

  describe('FileMemoryTracker integration', () => {
    it('should call trackMemory after successful BensyneClient.remember with correct args', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'agent-sessions' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledWith(
        '/home/user/docs/notes.md',
        'mem-abc',
        'watch-1',
        'agent-sessions',
        undefined,
        undefined,
      );
    });

    it('should call trackMemory for each successfully ingested chunk', async () => {
      const chunk1 = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      const chunk2 = aContentChunk({ chunkIndex: 1, memoryBank: 'vault' });
      mockBensyneClientService.remember
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-1', status: 'stored' }))
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-2', status: 'stored' }));
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      await useCase.execute({
        chunks: [chunk1, chunk2],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenNthCalledWith(
        1,
        '/home/user/docs/notes.md',
        'mem-1',
        'watch-1',
        'vault',
        undefined,
        undefined,
      );
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenNthCalledWith(
        2,
        '/home/user/docs/notes.md',
        'mem-2',
        'watch-1',
        'vault',
        undefined,
        undefined,
      );
    });

    it('should NOT call trackMemory when BensyneClient.remember fails', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(Result.ko([new Error('MCP error')]));

      await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(mockFileMemoryTrackerService.trackMemory).not.toHaveBeenCalled();
    });

    it('should NOT call trackMemory when BensyneClient.remember throws', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockRejectedValue(new Error('Network timeout'));

      await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(mockFileMemoryTrackerService.trackMemory).not.toHaveBeenCalled();
    });

    it('should track only successful chunks when some fail', async () => {
      const chunk1 = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      const chunk2 = aContentChunk({ chunkIndex: 1, memoryBank: 'vault' });
      const chunk3 = aContentChunk({ chunkIndex: 2, memoryBank: 'vault' });

      mockBensyneClientService.remember
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-1', status: 'stored' }))
        .mockResolvedValueOnce(Result.ko([new Error('MCP error')]))
        .mockResolvedValueOnce(Result.ok({ memory_id: 'mem-3', status: 'stored' }));
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      await useCase.execute({
        chunks: [chunk1, chunk2, chunk3],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledTimes(2);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenNthCalledWith(
        1,
        '/home/user/docs/notes.md',
        'mem-1',
        'watch-1',
        'vault',
        undefined,
        undefined,
      );
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenNthCalledWith(
        2,
        '/home/user/docs/notes.md',
        'mem-3',
        'watch-1',
        'vault',
        undefined,
        undefined,
      );
    });

    it('should not fail ingestion when trackMemory fails', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockRejectedValue(new Error('DB connection error'));

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(result.isOk()).toBe(true);
    });

    it('should not fail ingestion when trackMemory throws', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockRejectedValue(new Error('SQLite locked'));

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(result.isOk()).toBe(true);
    });

    it('should skip tracking when filePath is not present in metadata', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );

      await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: {},
      });

      expect(mockFileMemoryTrackerService.trackMemory).not.toHaveBeenCalled();
    });

    it('should skip tracking when metadata is undefined', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );

      await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
      });

      expect(mockFileMemoryTrackerService.trackMemory).not.toHaveBeenCalled();
    });

    it('should pass fileHash and hardwareId to trackMemory when provided', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
        fileHash: 'sha256-abc123',
        hardwareId: 'hw-id-456',
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledWith(
        '/home/user/docs/notes.md',
        'mem-abc',
        'watch-1',
        'vault',
        'sha256-abc123',
        'hw-id-456',
      );
    });

    it('should pass undefined fileHash and hardwareId when not provided', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledTimes(1);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledWith(
        '/home/user/docs/notes.md',
        'mem-abc',
        'watch-1',
        'vault',
        undefined,
        undefined,
      );
    });

    it('should pass fileHash only when hardwareId is absent', async () => {
      const chunk = aContentChunk({ chunkIndex: 0, memoryBank: 'vault' });
      mockBensyneClientService.remember.mockResolvedValue(
        Result.ok({ memory_id: 'mem-abc', status: 'stored' }),
      );
      mockFileMemoryTrackerService.trackMemory.mockResolvedValue(undefined);

      const result = await useCase.execute({
        chunks: [chunk],
        sourceId: 'watch-1',
        metadata: { filePath: '/home/user/docs/notes.md' },
        fileHash: 'sha256-only',
      });

      expect(result.isOk()).toBe(true);
      expect(mockFileMemoryTrackerService.trackMemory).toHaveBeenCalledWith(
        '/home/user/docs/notes.md',
        'mem-abc',
        'watch-1',
        'vault',
        'sha256-only',
        undefined,
      );
    });
  });
});
