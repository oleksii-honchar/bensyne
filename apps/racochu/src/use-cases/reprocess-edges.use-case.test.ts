import { Test, TestingModule } from '@nestjs/testing';
import { ReprocessEdgesUseCase } from './reprocess-edges.use-case';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { BensyneClient } from '../infrastructure/services/bensyne-client.service';
import { Result } from '../utils/result';

// Mock BensyneClient
const mockBensyneClient = {
  getFileChunks: jest.fn(),
  expandFileRelations: jest.fn(),
  prunePhantomEdgeStub: jest.fn(),
};

// Mock BasePinoLogger
const mockLogger: BasePinoLogger = {
  child: jest.fn().mockReturnThis(),
  debug: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
} as unknown as BasePinoLogger;

describe('ReprocessEdgesUseCase', () => {
  let useCase: ReprocessEdgesUseCase;
  let module: TestingModule;

  beforeEach(async () => {
    jest.clearAllMocks();

    module = await Test.createTestingModule({
      providers: [
        ReprocessEdgesUseCase,
        { provide: BensyneClient, useValue: mockBensyneClient },
        { provide: BasePinoLogger, useValue: mockLogger },
      ],
    }).compile();

    useCase = module.get<ReprocessEdgesUseCase>(ReprocessEdgesUseCase);
  });

  afterEach(async () => {
    await module.close();
  });

  it('should validate params and reject invalid source ID', async () => {
    const result = await useCase.execute({
      sourceId: '',
      sources: [],
      filePaths: [],
    });
    expect(result.isKo()).toBe(true);
  });

  it('should validate params and reject empty sources', async () => {
    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [],
      filePaths: [],
    });
    expect(result.isKo()).toBe(true);
  });

  it('should validate params and reject empty filePaths', async () => {
    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: [],
    });
    expect(result.isKo()).toBe(true);
  });

  it('should build file ID map and check edges for all files', async () => {
    // Mock getFileChunks to return file IDs
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'present',
        fileId: 'file-1',
        chunks: [
          { chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' },
        ],
      })
    );

    // Mock expandFileRelations to return no edges
    mockBensyneClient.expandFileRelations.mockResolvedValue(
      Result.ok([])
    );

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result.isOk()).toBe(true);
    expect(mockBensyneClient.getFileChunks).toHaveBeenCalledWith('/tmp/test/file1.md', 'test-bank');
    expect(mockBensyneClient.expandFileRelations).toHaveBeenCalledWith('file-1', 'test-bank', ['file_ref']);
  });

  it('should detect ghost edges and prune the phantom edge stub', async () => {
    // Mock getFileChunks: file exists, but edge target does not
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'present',
        fileId: 'file-1',
        chunks: [
          { chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' },
        ],
      })
    );

    // Edge points to a file ID that doesn't exist in our map
    mockBensyneClient.expandFileRelations.mockResolvedValue(
      Result.ok([
        { source_file_id: 'file-1', target_file_id: 'ghost-file', relation_type: 'file_ref' },
      ])
    );

    // Prune succeeds
    mockBensyneClient.prunePhantomEdgeStub.mockResolvedValue(Result.ok(undefined as unknown as void));

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result.isOk()).toBe(true);
    const stats = result.getValue();
    expect(stats.ghostEdgesFound).toBe(1);
    expect(stats.edgesNeedUpdate).toBe(1);
    expect(stats.edgesPruned).toBe(1);
    expect(mockBensyneClient.prunePhantomEdgeStub).toHaveBeenCalledWith(
      'file-1',
      'ghost-file',
      'test-bank',
      'file_ref'
    );
    expect(mockLogger.warn).toHaveBeenCalledWith(
      expect.stringContaining('Ghost edge found')
    );
    expect(mockLogger.info).toHaveBeenCalledWith(
      expect.stringContaining('Phantom edge stub pruned')
    );
  });

  it('should handle prune failures gracefully', async () => {
    // Mock getFileChunks: file exists, but edge target does not
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'present',
        fileId: 'file-1',
        chunks: [
          { chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' },
        ],
      })
    );

    // Edge points to a file ID that doesn't exist in our map
    mockBensyneClient.expandFileRelations.mockResolvedValue(
      Result.ok([
        { source_file_id: 'file-1', target_file_id: 'ghost-file', relation_type: 'file_ref' },
      ])
    );

    // Prune fails
    mockBensyneClient.prunePhantomEdgeStub.mockResolvedValue(
      Result.ko([{ message: 'prune failed', name: 'PruneFailed' }])
    );

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result.isOk()).toBe(true);
    const stats = result.getValue();
    expect(stats.ghostEdgesFound).toBe(1);
    expect(stats.edgesNeedUpdate).toBe(1);
    expect(stats.edgesPruned).toBe(0);
    expect(mockLogger.error).toHaveBeenCalledWith(
      expect.stringContaining('Failed to prune phantom edge stub')
    );
  });

  it('should not flag valid edges (target exists in map)', async () => {
    // Mock getFileChunks for two files
    mockBensyneClient.getFileChunks
      .mockResolvedValueOnce(
        Result.ok({
          status: 'present',
          fileId: 'file-1',
          chunks: [{ chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' }],
        })
      )
      .mockResolvedValueOnce(
        Result.ok({
          status: 'present',
          fileId: 'file-2',
          chunks: [{ chunkIndex: 0, contentHash: 'def', memoryStatus: 'present' }],
        })
      );

    // Edge from file-1 to file-2 (valid)
    mockBensyneClient.expandFileRelations
      .mockResolvedValueOnce(
        Result.ok([
          { source_file_id: 'file-1', target_file_id: 'file-2', relation_type: 'file_ref' },
        ])
      )
      .mockResolvedValueOnce(
        Result.ok([])
      );

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md', '/tmp/test/file2.md'],
    });

    expect(result.isOk()).toBe(true);
    const stats = result.getValue();
    expect(stats.ghostEdgesFound).toBe(0);
    expect(stats.edgesNeedUpdate).toBe(0);
  });

  it('should handle files with no chunks (FILE_NOT_FOUND)', async () => {
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'FILE_NOT_FOUND',
        chunks: [],
      })
    );

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result.isOk()).toBe(true);
    const stats = result.getValue();
    expect(stats.filesProcessed).toBe(1);
    expect(stats.ghostEdgesFound).toBe(0);
  });

  it('should handle expandFileRelations failure gracefully', async () => {
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'present',
        fileId: 'file-1',
        chunks: [{ chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' }],
      })
    );

    mockBensyneClient.expandFileRelations.mockResolvedValue(
      Result.ko([{ message: 'expand failed', name: 'ExpandFailed' }])
    );

    const result = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result.isOk()).toBe(true);
    const stats = result.getValue();
    expect(stats.filesProcessed).toBe(1);
    expect(stats.ghostEdgesFound).toBe(0);
  });

  it('should be idempotent (safe to run multiple times)', async () => {
    mockBensyneClient.getFileChunks.mockResolvedValue(
      Result.ok({
        status: 'present',
        fileId: 'file-1',
        chunks: [{ chunkIndex: 0, contentHash: 'abc', memoryStatus: 'present' }],
      })
    );

    mockBensyneClient.expandFileRelations.mockResolvedValue(
      Result.ok([])
    );

    const result1 = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    const result2 = await useCase.execute({
      sourceId: 'test-source',
      sources: [
        {
          id: 'test-source',
          path: '/tmp/test',
          sourceType: 'agent-persona',
          memoryBank: 'test-bank',
        },
      ],
      filePaths: ['/tmp/test/file1.md'],
    });

    expect(result1.isOk()).toBe(true);
    expect(result2.isOk()).toBe(true);
  });
});
