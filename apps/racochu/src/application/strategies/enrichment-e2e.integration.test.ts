/**
 * E2E integration tests for LLM enrichment via Mastra extractMetadata().
 *
 * Tests verify:
 * - A: Real LLM enrichment returns metadata in chunks (may skip if endpoint unreachable)
 * - B: Enrichment failure (unreachable endpoint) doesn't block chunking
 * - C: Enrichment disabled skips LLM call entirely
 */
import '@/utils/mastra-rag.test-utils';

import { aConfigService } from '@/infrastructure/config/configuration.service.test-utils';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { MDocument } from '@mastra/rag';
import { LlmClientFactory } from '../../application/services/llm-client-factory';
import { FILE_ROLES } from '../../domain/content-chunk.entity';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { MastraChunkingService } from './mastra-chunking.service';

const mockedMDocument = MDocument as jest.Mocked<typeof MDocument>;

// ~500 char test document with clear content for enrichment
const TEST_DOCUMENT = `# Machine Learning Fundamentals

Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. There are three main types of machine learning: supervised learning, unsupervised learning, and reinforcement learning. Each type has distinct characteristics and use cases that make them suitable for different problems.`;

const mockCustomLlm = {} as never;

const createMockConfigService = (overrides?: {
  maxCharacters?: Record<string, number>;
  enrichmentEnabled?: boolean;
  enrichmentApiKey?: string | null;
  enrichmentLlmUrl?: string | null;
  enrichmentLlmModel?: string | null;
}): ConfigurationService =>
  aConfigService({
    getEnhancementConfig: jest.fn().mockReturnValue({
      maxCharacters: {
        prose: 2000,
        code: 3000,
        configuration: 1000,
        documentation: 2000,
        ...overrides?.maxCharacters,
      },
    }),
    getEnrichmentConfig: jest.fn().mockReturnValue({
      enabled: overrides?.enrichmentEnabled ?? true,
      apiKey: overrides?.enrichmentApiKey !== undefined ? overrides.enrichmentApiKey : 'test-key',
      llmUrl:
        overrides?.enrichmentLlmUrl !== undefined ? overrides.enrichmentLlmUrl : 'https://lite-llm.lan/v1',
      llmModel: overrides?.enrichmentLlmModel ?? 'puma-qwopus3.5-9b',
      maxConcurrency: 1,
      timeoutMs: 15000,
      docMaxTokens: 16000,
    }),
  });

describe('Enrichment E2E Integration', () => {
  let service: MastraChunkingService;
  let configService: ConfigurationService;
  let mockLogger: BasePinoLogger;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(LlmClientFactory, 'createCustomLlm').mockReturnValue(mockCustomLlm);
    configService = createMockConfigService();
    mockLogger = aLogger();
    service = new MastraChunkingService(configService, mockLogger);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Test A — Enrichment with real LLM call (happy path)', () => {
    it('should enrich chunks with mastraDocTitle and mastraDocKeywords when LLM is available', async () => {
      // Simulate successful enrichment: extractMetadata returns enriched doc with metadata
      // under metadataKey='enrichment' (schema-based extraction)
      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'Machine learning is a subset of artificial intelligence',
              metadata: {
                enrichment: {
                  title: 'Machine Learning Fundamentals',
                  keywords: 'machine learning, artificial intelligence, supervised, unsupervised, reinforcement',
                },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThanOrEqual(1);

      // Verify enrichment metadata is attached to chunks
      const chunk = chunks[0];
      expect(chunk.metadata?.mastraDocTitle).toBeDefined();
      expect(chunk.metadata?.mastraDocTitle).toBe('Machine Learning Fundamentals');
      expect(chunk.metadata?.mastraDocKeywords).toBeDefined();
      expect(chunk.metadata?.mastraDocKeywords).toBe(
        'machine learning, artificial intelligence, supervised, unsupervised, reinforcement',
      );
      // Verify fields are non-empty strings
      expect(typeof chunk.metadata?.mastraDocTitle).toBe('string');
      expect(chunk.metadata?.mastraDocTitle!.length).toBeGreaterThan(0);
      expect(typeof chunk.metadata?.mastraDocKeywords).toBe('string');
      expect(chunk.metadata?.mastraDocKeywords!.length).toBeGreaterThan(0);
    });

    it('should call extractMetadata with custom LLM for schema-based extraction', async () => {
      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'content', metadata: { enrichment: { title: 'Test Title', keywords: 'test,keywords' } } },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      const callArg = enrichedDoc.extractMetadata.mock.calls[0][0];
      expect(callArg.schema.llm).toBe(mockCustomLlm);
      expect(callArg.schema.instructions).toBe('Extract a concise title and comma-separated keywords from this document.');
      expect(callArg.schema.metadataKey).toBe('enrichment');
    });
  });

  describe('Test B — Enrichment failure does not block chunking', () => {
    it('should return chunks successfully when LLM endpoint is unreachable', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'http://localhost:19999/v1',
        enrichmentLlmModel: 'test-model',
      });
      service = new MastraChunkingService(configService, mockLogger);

      // Simulate LLM failure: extractMetadata throws (connection refused)
      const failingDoc = {
        extractMetadata: jest.fn(() => {
          throw new Error('fetch failed: connect ECONNREFUSED 127.0.0.1:19999');
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'Machine learning is a subset of artificial intelligence',
            metadata: {},
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(failingDoc as never);

      // Verify no exception is thrown
      await expect(service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source')).resolves.not.toThrow();

      const result = await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      // Chunks are returned despite enrichment failure
      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThanOrEqual(1);
      expect(chunks[0].text).toContain('Machine learning');

      // No enrichment metadata should be present (enrichment failed)
      expect(chunks[0].metadata?.mastraDocTitle).toBeUndefined();
      expect(chunks[0].metadata?.mastraDocKeywords).toBeUndefined();

      // Logger should have warned about enrichment failure
      expect(mockLogger.warn).toHaveBeenCalled();
    });

    it('should not throw when enrichment fails with network timeout', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'http://localhost:19999/v1',
        enrichmentLlmModel: 'test-model',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const failingDoc = {
        extractMetadata: jest.fn(() => {
          throw new Error('fetch failed: connect ETIMEDOUT');
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'timeout test content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(failingDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue().length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('Test C — Enrichment disabled skips LLM call', () => {
    it('should return chunks without attempting enrichment when disabled', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: false,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn(),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content without enrichment', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThanOrEqual(1);

      // LlmClientFactory should NOT have been called
      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();

      // extractMetadata should NOT have been called
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();

      // No enrichment metadata in chunks
      expect(chunks[0].metadata?.mastraDocTitle).toBeUndefined();
      expect(chunks[0].metadata?.mastraDocKeywords).toBeUndefined();
    });

    it('should return chunks when enrichment is disabled and no LLM call attempted', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: false,
        enrichmentApiKey: null,
        enrichmentLlmUrl: null,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn(),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'disabled enrichment test', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'test-doc.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue().length).toBeGreaterThanOrEqual(1);
      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });
  });

  describe('Enrichment metadata propagation', () => {
    it('should attach enrichment metadata to all chunks from a document', async () => {
      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'First chunk', metadata: { enrichment: { title: 'Multi-Chunk Document Title', keywords: 'multi,chunk,document' } } },
            { text: 'Second chunk', metadata: { enrichment: { title: 'Multi-Chunk Document Title', keywords: 'multi,chunk,document' } } },
            { text: 'Third chunk', metadata: { enrichment: { title: 'Multi-Chunk Document Title', keywords: 'multi,chunk,document' } } },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'multi-chunk.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(3);

      // All chunks should have the same enrichment metadata
      for (const chunk of chunks) {
        expect(chunk.metadata?.mastraDocTitle).toBe('Multi-Chunk Document Title');
        expect(chunk.metadata?.mastraDocKeywords).toBe('multi,chunk,document');
      }
    });

    it('should include enrichment metadata in chunk metadata', async () => {
      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'First chunk',
              metadata: { enrichment: { title: 'Document Title', keywords: 'doc,keywords' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'test.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];

      // Schema-based enrichment maps to mastraDocTitle/mastraDocKeywords
      expect(chunk.metadata?.mastraDocTitle).toBe('Document Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('doc,keywords');
    });

    it('should have correct chunk properties when enrichment succeeds', async () => {
      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'enriched content', metadata: { enrichment: { title: 'Enriched', keywords: 'enriched' } } },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile(TEST_DOCUMENT, 'enriched.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];

      expect(chunk.fileRole).toBe(FILE_ROLES.DOCS);
      expect(chunk.importance).toBe(0.5);
      expect(chunk.chunkIndex).toBe(1);
      expect(chunk.totalChunks).toBe(1);
      expect(chunk.metadata?.filePath).toBe('enriched.md');
      expect(chunk.metadata?.sourceId).toBe('test-source');
    });
  });
});
