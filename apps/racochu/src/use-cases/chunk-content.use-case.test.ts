import '@/utils/mastra-rag.test-utils';

import * as crypto from 'crypto';
import { EnhancementPipelineService } from '../application/services/enhancement-pipeline.service';
import { BaseChunkingStrategy } from '../application/strategies/base-chunking-strategy';
import { StrategyRouter } from '../application/strategies/strategy-router.service';
import { aContentChunk } from '../domain/content-chunk.entity.test-utils';
import { EnhancementConfig, WatchSourceConfig } from '../infrastructure/config/config-schemas';
import { ConfigurationService } from '../infrastructure/config/configuration.service';
import { SOURCE_STRATEGIES } from '../infrastructure/config/source-strategies';
import { BasePinoLogger } from '../infrastructure/logging/base-pino-logger';
import { aLogger } from '../infrastructure/logging/logger.test-utils';
import { Result } from '../utils/result';
import { ChunkContentUseCase } from './chunk-content.use-case';

// Node's crypto module is frozen (jest.spyOn cannot redefine createHash), so the
// module is mocked with a controllable createHash that delegates to the real
// implementation by default. This lets tests force the non-fatal failure path
// while still asserting against genuine sha256 digests.
jest.mock('crypto', () => ({ createHash: jest.fn() }));
const mockedCreateHash = crypto.createHash as unknown as jest.Mock;
const realCrypto = jest.requireActual<typeof crypto>('crypto');
const sha256 = (text: string) => realCrypto.createHash('sha256').update(text).digest('hex');

const defaultEnhancementConfig: EnhancementConfig = {
  maxCharacters: { prose: 200, code: 400, configuration: 300, documentation: 300 },
  importance: {
    enabled: true,
    defaultScore: 0.5,
    factors: [
      { name: 'fileRole', weight: 0.4 },
      { name: 'length', weight: 0.2 },
      { name: 'keywords', weight: 0.3 },
      { name: 'header', weight: 0.1 },
    ],
  },
  tags: { enabled: true, maxTags: 10 },
  source: { includePath: true, includeSection: true, includeMetadata: false },
};

const defaultSourceConfig: WatchSourceConfig = {
  id: 'test-source',
  path: '/test/path',
  memoryBank: 'test-memoryBank',
  exclude: [],
  debounceMs: 3000,
  strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
};

describe('ChunkContentUseCase', () => {
  let useCase: ChunkContentUseCase;
  let mockStrategyRouter: jest.Mocked<{ selectStrategy: jest.Mock }>;
  let mockStrategy: jest.Mocked<{ chunkFile: jest.Mock }>;
  let mockEnhancementPipelineService: jest.Mocked<{ enhance: jest.Mock }>;
  let mockConfigurationService: jest.Mocked<{ getEnhancementConfig: jest.Mock }>;
  let mockLogger: jest.Mocked<BasePinoLogger>;

  beforeEach(() => {
    mockStrategy = {
      chunkFile: jest.fn(),
    };

    mockStrategyRouter = {
      selectStrategy: jest.fn().mockReturnValue(mockStrategy as unknown as BaseChunkingStrategy),
    };

    mockEnhancementPipelineService = {
      enhance: jest.fn().mockImplementation(chunks => Promise.resolve(Result.ok(chunks))),
    };

    mockConfigurationService = {
      getEnhancementConfig: jest.fn(() => defaultEnhancementConfig),
    };

    mockLogger = aLogger();

    // Default: real sha256. Individual tests override to force the failure path.
    mockedCreateHash.mockImplementation(realCrypto.createHash);

    useCase = new ChunkContentUseCase(
      mockStrategyRouter as unknown as StrategyRouter,
      mockEnhancementPipelineService as unknown as EnhancementPipelineService,
      mockConfigurationService as unknown as ConfigurationService,
      mockLogger as unknown as BasePinoLogger,
    );
  });

  describe('execute with valid params', () => {
    it('should return chunks when chunking succeeds', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.ts';
      const sourceId = 'test-source';
      const chunks = [aContentChunk({ text: 'chunk 1' }), aContentChunk({ text: 'chunk 2' })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      const result = await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
      const returned = result.getValue();
      expect(returned).toHaveLength(2);
      expect(returned[0].text).toBe('chunk 1');
      expect(returned[1].text).toBe('chunk 2');
      // chunkHash is always injected (sha256 of the exact chunk text)
      expect(returned[0].metadata?.chunkHash).toBe(sha256('chunk 1'));
      expect(returned[1].metadata?.chunkHash).toBe(sha256('chunk 2'));
    });

    it('should call StrategyRouter.selectStrategy with sourceConfig', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalledWith(defaultSourceConfig);
    });

    it('should call selected strategy.chunkFile with content, filePath, sourceId, sourceConfig', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategy.chunkFile).toHaveBeenCalledWith(content, filePath, sourceId, defaultSourceConfig);
    });

    it('should select strategy and chunk for markdown files', async () => {
      const content = '# Title\n\nContent';
      const filePath = '/path/to/README.md';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalled();
      expect(mockStrategy.chunkFile).toHaveBeenCalled();
    });

    it('should select strategy and chunk for TypeScript files', async () => {
      const content = 'const x = 1;';
      const filePath = '/path/to/app.ts';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalled();
      expect(mockStrategy.chunkFile).toHaveBeenCalled();
    });

    it('should select strategy and chunk for JSON config files', async () => {
      const content = '{"key": "value"}';
      const filePath = '/path/to/config.json';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalled();
      expect(mockStrategy.chunkFile).toHaveBeenCalled();
    });

    it('should select strategy and chunk for plain text files', async () => {
      const content = 'First sentence. Second sentence.';
      const filePath = '/path/to/notes.txt';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalled();
      expect(mockStrategy.chunkFile).toHaveBeenCalled();
    });

    it('should fallback to content-aware strategy when sourceConfig is not provided', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.ts';
      const sourceId = 'test-source';
      const chunks = [aContentChunk()];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(chunks));

      await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
      });

      expect(mockStrategyRouter.selectStrategy).toHaveBeenCalledWith(
        expect.objectContaining({
          strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
          id: sourceId,
          path: filePath,
          memoryBank: 'test-memoryBank',
        }),
      );
    });
  });

  describe('execute with invalid params', () => {
    it('should return error when content is missing', async () => {
      const result = await useCase.execute({
        content: '',
        filePath: '/path/to/file.ts',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
      });

      expect(result.isKo()).toBe(true);
    });

    it('should return error when filePath is missing', async () => {
      const result = await useCase.execute({
        content: 'test',
        filePath: '',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
      });

      expect(result.isKo()).toBe(true);
    });

    it('should return error when sourceId is missing', async () => {
      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.ts',
        sourceId: '',
        memoryBank: 'test-memoryBank',
      });

      expect(result.isKo()).toBe(true);
    });

    it('should return error when maxTokens is negative', async () => {
      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.ts',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
        maxTokens: -10,
      });

      expect(result.isKo()).toBe(true);
    });

    it('should return error when overlapTokens is negative', async () => {
      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.ts',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
        overlapTokens: -10,
      });

      expect(result.isKo()).toBe(true);
    });
  });

  describe('strategy guard', () => {
    it('should return StrategySelectionError when strategyRouter returns undefined', async () => {
      mockStrategyRouter.selectStrategy.mockReturnValue(undefined);

      const result = await useCase.execute({
        content: 'Test content',
        filePath: '/path/to/file.ts',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toBe('No chunking strategy selected for sourceId="test-source"');
      expect((result.getErrors()[0] as any).code).toBe('StrategySelectionError');
      expect(mockStrategy.chunkFile).not.toHaveBeenCalled();
    });

    it('should return StrategySelectionError when no sourceConfig and router returns undefined', async () => {
      mockStrategyRouter.selectStrategy.mockReturnValue(undefined);

      const result = await useCase.execute({
        content: 'Test content',
        filePath: '/path/to/file.ts',
        sourceId: 'test-source',
        memoryBank: 'test-memoryBank',
      });

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toBe('No chunking strategy selected for sourceId="test-source"');
      expect((result.getErrors()[0] as any).code).toBe('StrategySelectionError');
    });
  });

  describe('error handling', () => {
    it('should return error when chunking fails', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.ts';
      const sourceId = 'test-source';

      mockStrategy.chunkFile.mockResolvedValue(Result.ko([new Error('Chunking failed')]));

      const result = await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank: 'test-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toBe('Chunking failed');
    });
  });

  describe('enhancement pipeline integration', () => {
    it('should pipe chunks through EnhancementPipelineService after chunking', async () => {
      const content = 'Test content';
      const filePath = '/path/to/file.md';
      const sourceId = 'test-source';
      const memoryBank = 'my-memoryBank';
      const rawChunks = [
        aContentChunk({ text: 'raw chunk 1', importance: 0.5, tags: [], memoryBank: 'default' }),
      ];
      const enhancedChunks = [
        aContentChunk({ text: 'raw chunk 1', importance: 0.8, tags: ['tag1'], memoryBank: 'my-memoryBank' }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(enhancedChunks));

      const result = await useCase.execute({
        content,
        filePath,
        sourceId,
        memoryBank,
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
      const returned = result.getValue();
      expect(returned).toHaveLength(1);
      // Enhanced values returned (not raw), proving the pipeline ran
      expect(returned[0].text).toBe('raw chunk 1');
      expect(returned[0].importance).toBe(0.8);
      expect(returned[0].tags).toEqual(['tag1']);
      expect(returned[0].memoryBank).toBe('my-memoryBank');
      expect(mockEnhancementPipelineService.enhance).toHaveBeenCalledWith(
        rawChunks,
        sourceId,
        memoryBank,
        defaultEnhancementConfig,
      );
    });

    it('should return enhanced chunks not raw chunks', async () => {
      const rawChunks = [aContentChunk({ text: 'raw', importance: 0.5, tags: [], memoryBank: 'default' })];
      const enhancedChunks = [
        aContentChunk({ text: 'raw', importance: 0.9, tags: ['important'], memoryBank: 'test-ns' }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(enhancedChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'test-ns',
        sourceConfig: defaultSourceConfig,
      });

      const returnedChunks = result.getValue();
      expect(returnedChunks[0].importance).toBe(0.9);
      expect(returnedChunks[0].tags).toEqual(['important']);
      expect(returnedChunks[0].memoryBank).toBe('test-ns');
    });

    it('should include memoryBank in params and pass to EnhancementPipelineService', async () => {
      mockStrategy.chunkFile.mockResolvedValue(Result.ok([aContentChunk()]));
      mockEnhancementPipelineService.enhance.mockResolvedValue(
        Result.ok([aContentChunk({ memoryBank: 'custom-ns' })]),
      );

      await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'custom-ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockEnhancementPipelineService.enhance).toHaveBeenCalledWith(
        expect.any(Array),
        'src',
        'custom-ns',
        defaultEnhancementConfig,
      );
    });

    it('should fallback to raw chunks when enhancement fails', async () => {
      const rawChunks = [aContentChunk({ text: 'raw chunk' })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(
        Result.ko([new Error('Enhancement pipeline failed')]),
      );

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
      const returned = result.getValue();
      expect(returned).toHaveLength(1);
      expect(returned[0].text).toBe('raw chunk');
    });

    it('should use enhancement config from ConfigurationService', async () => {
      const customConfig: EnhancementConfig = {
        ...defaultEnhancementConfig,
        importance: { ...defaultEnhancementConfig.importance, defaultScore: 0.8 },
      };
      mockConfigurationService.getEnhancementConfig.mockReturnValue(customConfig);

      mockStrategy.chunkFile.mockResolvedValue(Result.ok([aContentChunk()]));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok([aContentChunk()]));

      await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(mockConfigurationService.getEnhancementConfig).toHaveBeenCalled();
      expect(mockEnhancementPipelineService.enhance).toHaveBeenCalledWith(
        expect.any(Array),
        'src',
        'ns',
        customConfig,
      );
    });
  });

  describe('memoryBank validation', () => {
    it('should accept valid memoryBank in params', async () => {
      mockStrategy.chunkFile.mockResolvedValue(Result.ok([aContentChunk()]));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok([aContentChunk()]));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'valid-memoryBank',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
    });

    it('should return error when memoryBank is empty', async () => {
      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: '',
      });

      expect(result.isKo()).toBe(true);
    });
  });

  describe('fileHash and hardwareId metadata injection', () => {
    it('should inject fileHash into each chunk metadata when provided', async () => {
      const fileHash = 'abc123def456';
      const rawChunks = [
        aContentChunk({ text: 'chunk 1', metadata: { filePath: '/test.md' } }),
        aContentChunk({ text: 'chunk 2', metadata: { filePath: '/test.md' } }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBe(fileHash);
      expect(chunks[1].metadata?.fileHash).toBe(fileHash);
    });

    it('should inject hardwareId into each chunk metadata when provided', async () => {
      const hardwareId = 'hw-uuid-12345';
      const rawChunks = [
        aContentChunk({ text: 'chunk 1', metadata: { filePath: '/test.md' } }),
        aContentChunk({ text: 'chunk 2', metadata: { filePath: '/test.md' } }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        hardwareId,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.hardwareId).toBe(hardwareId);
      expect(chunks[1].metadata?.hardwareId).toBe(hardwareId);
    });

    it('should inject both fileHash and hardwareId into chunk metadata', async () => {
      const fileHash = 'sha256-hash';
      const hardwareId = 'hw-id';
      const rawChunks = [
        aContentChunk({ text: 'chunk 1', metadata: { filePath: '/test.md' } }),
        aContentChunk({ text: 'chunk 2', metadata: { filePath: '/test.md' } }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
        hardwareId,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBe(fileHash);
      expect(chunks[0].metadata?.hardwareId).toBe(hardwareId);
      expect(chunks[1].metadata?.fileHash).toBe(fileHash);
      expect(chunks[1].metadata?.hardwareId).toBe(hardwareId);
    });

    it('should merge fileHash and hardwareId with existing chunk metadata', async () => {
      const fileHash = 'sha256-hash';
      const hardwareId = 'hw-id';
      const existingMetadata = { filePath: '/test.md', customKey: 'customValue' };
      const rawChunks = [aContentChunk({ text: 'chunk 1', metadata: existingMetadata })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
        hardwareId,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBe(fileHash);
      expect(chunks[0].metadata?.hardwareId).toBe(hardwareId);
      expect(chunks[0].metadata?.filePath).toBe('/test.md');
      expect(chunks[0].metadata?.customKey).toBe('customValue');
    });

    it('should initialize metadata object when chunk has no metadata', async () => {
      const fileHash = 'sha256-hash';
      const hardwareId = 'hw-id';
      const rawChunks = [aContentChunk({ text: 'chunk 1', metadata: undefined })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
        hardwareId,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBe(fileHash);
      expect(chunks[0].metadata?.hardwareId).toBe(hardwareId);
    });

    it('should not add fileHash or hardwareId when neither is provided', async () => {
      const rawChunks = [aContentChunk({ text: 'chunk 1', metadata: { filePath: '/test.md' } })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBeUndefined();
      expect(chunks[0].metadata?.hardwareId).toBeUndefined();
    });

    it('should inject fileHash and hardwareId after enhancement pipeline', async () => {
      const fileHash = 'sha256-hash';
      const hardwareId = 'hw-id';
      const rawChunks = [aContentChunk({ text: 'raw', metadata: {} })];
      const enhancedChunks = [aContentChunk({ text: 'enhanced', metadata: { enhanced: 'true' } })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(enhancedChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
        hardwareId,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.fileHash).toBe(fileHash);
      expect(chunks[0].metadata?.hardwareId).toBe(hardwareId);
      expect(chunks[0].metadata?.enhanced).toBe('true');
    });

    it('should share the same fileHash across all chunks from the same file', async () => {
      const fileHash = 'shared-hash';
      const rawChunks = [
        aContentChunk({ text: 'chunk 1', metadata: {} }),
        aContentChunk({ text: 'chunk 2', metadata: {} }),
        aContentChunk({ text: 'chunk 3', metadata: {} }),
      ];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: 'test',
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const allHashes = chunks.map(c => c.metadata?.fileHash);
      expect(allHashes).toEqual([fileHash, fileHash, fileHash]);
    });
  });

  describe('chunkHash computation', () => {
    it('computes chunkHash = sha256 of the exact chunk text for each chunk (normalization-drift guard)', async () => {
      const textA = 'chunk alpha content';
      const textB = 'chunk beta content';
      const rawChunks = [aContentChunk({ text: textA }), aContentChunk({ text: textB })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        // Full content differs from each chunk's text — the hash must be of the
        // chunk text as sent, NOT the whole content or a normalized variant.
        content: textA + '\n\n' + textB,
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.chunkHash).toBe(sha256(textA));
      expect(chunks[1].metadata?.chunkHash).toBe(sha256(textB));
      // Distinct texts ⇒ distinct hashes (guard against a constant/wrong input)
      expect(chunks[0].metadata?.chunkHash).not.toBe(chunks[1].metadata?.chunkHash);
    });

    it('includes chunkHash alongside fileHash in chunk metadata', async () => {
      const fileHash = 'file-hash-abc';
      const text = 'some chunk text';
      const rawChunks = [aContentChunk({ text, metadata: {} })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));

      const result = await useCase.execute({
        content: text,
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
      });

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.chunkHash).toBe(sha256(text));
      expect(chunk.metadata?.fileHash).toBe(fileHash);
    });

    it('omits chunkHash (non-fatal) when hash computation throws, without failing the use case', async () => {
      const text = 'chunk text';
      const rawChunks = [aContentChunk({ text, metadata: {} })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));
      mockedCreateHash.mockImplementation(() => {
        throw new Error('crypto boom');
      });

      const result = await useCase.execute({
        content: text,
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
      });

      expect(result.isOk()).toBe(true); // non-fatal: no throw
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.chunkHash).toBeUndefined(); // key omitted
      expect(chunk.text).toBe(text); // chunk still produced
    });

    it('still injects fileHash when chunkHash computation fails', async () => {
      const fileHash = 'file-hash-abc';
      const text = 'chunk text';
      const rawChunks = [aContentChunk({ text, metadata: {} })];

      mockStrategy.chunkFile.mockResolvedValue(Result.ok(rawChunks));
      mockEnhancementPipelineService.enhance.mockResolvedValue(Result.ok(rawChunks));
      mockedCreateHash.mockImplementation(() => {
        throw new Error('crypto boom');
      });

      const result = await useCase.execute({
        content: text,
        filePath: '/path/to/file.md',
        sourceId: 'src',
        memoryBank: 'ns',
        sourceConfig: defaultSourceConfig,
        fileHash,
      });

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.chunkHash).toBeUndefined();
      expect(chunk.metadata?.fileHash).toBe(fileHash);
    });
  });
});
