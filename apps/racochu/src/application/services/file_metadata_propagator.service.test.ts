import { Test, TestingModule } from '@nestjs/testing';
import { FILE_ROLES } from '../../domain/content-chunk.entity';
import { aContentChunk } from '../../domain/content-chunk.entity.test-utils';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { aLogger } from '../../infrastructure/logging/logger.test-utils';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { BENSYNE_FILE_CLIENT, BensyneFileClient, FileMetadataPropagator } from './file_metadata_propagator.service';

describe('FileMetadataPropagator', () => {
  let service: FileMetadataPropagator;
  let bensyneClient: jest.Mocked<BensyneFileClient>;
  let logger: jest.Mocked<BasePinoLogger>;

  beforeEach(async () => {
    bensyneClient = {
      upsertFile: jest.fn(),
      createChunk: jest.fn(),
    } as unknown as jest.Mocked<BensyneFileClient>;

    logger = aLogger();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        FileMetadataPropagator,
        { provide: BENSYNE_FILE_CLIENT, useValue: bensyneClient },
        { provide: BasePinoLogger, useValue: logger },
      ],
    }).compile();

    service = module.get<FileMetadataPropagator>(FileMetadataPropagator);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('propagateFileMetadata', () => {
    describe('happy path', () => {
      it('should extract file metadata from chunk and upsert file in bensyne', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          fileRole: FILE_ROLES.CODE,
          language: 'typescript',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
          tags: ['typescript', 'code'],
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_123');

        expect(result.isOk()).toBe(true);
        expect(bensyneClient.upsertFile).toHaveBeenCalledTimes(1);
        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.path).toBe('/test/path/file.ts');
        expect(upsertCall.source_type).toBe('file_system');
        expect(upsertCall.language).toBe('typescript');
        expect(upsertCall.aggregated_tags).toEqual(['typescript', 'code']);
      });

      it('should create a file chunk linking file to memory', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          chunkIndex: 2,
          startLine: 10,
          endLine: 50,
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_456');

        expect(bensyneClient.createChunk).toHaveBeenCalledWith({
          file_id: 'file_1',
          memory_id: 'mem_456',
          chunk_index: 2,
          start_line: 10,
          end_line: 50,
        });
      });

      it('should return Result.ok with file_id and chunk_id on success', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_789');

        expect(result.isOk()).toBe(true);
        const value = result.getValue();
        expect(value.file_id).toBe('file_1');
        expect(value.chunk_id).toBe('fc_1');
      });

      it('should handle DOCS file role without language', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/README.md',
          fileRole: FILE_ROLES.DOCS,
          metadata: { filePath: '/test/path/README.md', sourceId: 'file_system' },
          language: undefined,
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_2', path: '/test/path/README.md' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_2' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_abc');

        expect(result.isOk()).toBe(true);
        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.language).toBeUndefined();
      });

      it('should handle CONFIG file role', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/tsconfig.json',
          fileRole: FILE_ROLES.CONFIG,
          metadata: { filePath: '/test/path/tsconfig.json', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_3', path: '/test/path/tsconfig.json' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_3' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_def');

        expect(result.isOk()).toBe(true);
        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.path).toBe('/test/path/tsconfig.json');
      });
    });

    describe('source type mapping', () => {
      it('should map sourceId "file_system" to source_type "file_system"', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.source_type).toBe('file_system');
      });

      it('should map sourceId "agent_session" to source_type "agent_session"', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/session.md',
          metadata: { filePath: '/test/path/session.md', sourceId: 'agent_session' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/session.md' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.source_type).toBe('agent_session');
      });

      it('should default to "unknown" source_type when sourceId is missing', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.source_type).toBe('unknown');
      });
    });

    describe('file path extraction', () => {
      it('should extract file path from metadata.filePath when available', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/custom/path/file.ts' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/custom/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.path).toBe('/custom/path/file.ts');
      });

      it('should fall back to breadcrumb when metadata.filePath is missing', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: {},
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.path).toBe('/test/path/file.ts');
      });

      it('should return Result.ko when no file path can be extracted', async () => {
        const chunk = aContentChunk({
          breadcrumb: '',
          metadata: {},
        });

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isKo()).toBe(true);
        expect(bensyneClient.upsertFile).not.toHaveBeenCalled();
        expect(bensyneClient.createChunk).not.toHaveBeenCalled();
      });
    });

    describe('error handling', () => {
      it('should return Result.ko when upsertFile fails', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(
          Result.ko([new ErrorWithDetails('Database error', 'UpsertFailed')]),
        );

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isKo()).toBe(true);
        expect(bensyneClient.createChunk).not.toHaveBeenCalled();
      });

      it('should return Result.ko when createChunk fails but file was upserted', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(
          Result.ko([new ErrorWithDetails('Chunk creation failed', 'ChunkFailed')]),
        );

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isKo()).toBe(true);
      });

      it('should return Result.ko when bensyne client throws an exception', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockRejectedValue(new Error('Connection refused'));

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isKo()).toBe(true);
        expect(bensyneClient.createChunk).not.toHaveBeenCalled();
      });

      it('should propagate failure without breaking the pipeline (no throw)', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockRejectedValue(new Error('Network error'));

        // Should not throw — propagation failure is non-fatal
        await expect(service.propagateFileMetadata(chunk, 'mem_1')).resolves.not.toThrow();
      });
    });

    describe('chunk metadata mapping', () => {
      it('should include chunk_index from ContentChunk', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          chunkIndex: 5,
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const createChunkCall = bensyneClient.createChunk.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(createChunkCall.chunk_index).toBe(5);
      });

      it('should include start_line and end_line when available', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          startLine: 100,
          endLine: 200,
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const createChunkCall = bensyneClient.createChunk.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(createChunkCall.start_line).toBe(100);
        expect(createChunkCall.end_line).toBe(200);
      });

      it('should omit start_line and end_line when undefined', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          startLine: undefined,
          endLine: undefined,
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const createChunkCall = bensyneClient.createChunk.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(createChunkCall.start_line).toBeUndefined();
        expect(createChunkCall.end_line).toBeUndefined();
      });
    });

    describe('tags and keywords propagation', () => {
      it('should propagate tags from chunk to file aggregated_tags', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
          tags: ['typescript', 'api', 'controller'],
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.aggregated_tags).toEqual(['typescript', 'api', 'controller']);
      });

      it('should propagate empty tags array when chunk has no tags', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/file.ts',
          metadata: { filePath: '/test/path/file.ts', sourceId: 'file_system' },
          tags: [],
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        await service.propagateFileMetadata(chunk, 'mem_1');

        const upsertCall = bensyneClient.upsertFile.mock.calls[0][0] as unknown as Record<string, unknown>;
        expect(upsertCall.aggregated_tags).toEqual([]);
      });
    });

    describe('edge cases', () => {
      it('should handle empty breadcrumb with metadata.filePath', async () => {
        const chunk = aContentChunk({
          breadcrumb: '',
          metadata: { filePath: '/only/in/metadata.ts' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/only/in/metadata.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isOk()).toBe(true);
      });

      it('should handle chunk with oversized flag', async () => {
        const chunk = aContentChunk({
          breadcrumb: '/test/path/large-file.ts',
          oversized: true,
          metadata: { filePath: '/test/path/large-file.ts', sourceId: 'file_system' },
        });

        bensyneClient.upsertFile.mockResolvedValue(Result.ok({ id: 'file_1', path: '/test/path/large-file.ts' }));
        bensyneClient.createChunk.mockResolvedValue(Result.ok({ id: 'fc_1' }));

        const result = await service.propagateFileMetadata(chunk, 'mem_1');

        expect(result.isOk()).toBe(true);
      });
    });
  });
});
