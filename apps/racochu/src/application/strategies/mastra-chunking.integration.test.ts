/**
 * Integration test: Full chunking pipeline with UTF-8 rich content (Cyrillic)
 * that generates chunks exceeding the server request body limit.
 *
 * Verifies that the MastraChunkingService:
 * - Splits content into chunks
 * - Clamps oversized chunks to fit within the 4032-byte server request body limit
 * - Produces clean UTF-8 boundaries (no half-characters)
 * - Does not produce any `remember request too large` errors
 */
import '@/utils/mastra-rag.test-utils';

import { MDocument } from '@mastra/rag';
import { ConfigurationService } from '@/infrastructure/config/configuration.service';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { MastraChunkingService } from './mastra-chunking.service';
import { clampUtf8 } from './utf8-clamp';

const mockedMDocument = MDocument as jest.Mocked<typeof MDocument>;

describe('MastraChunkingService Integration — UTF-8 Rich Content Over Request Body Limit', () => {
  let service: MastraChunkingService;
  let configService: ConfigurationService;
  let mockLogger: BasePinoLogger;

  const ENHANCEMENT_CONFIG = {
    maxChunkBytes: 3200,
    serverRequestBodyLimit: 4032,
    maxCharacters: {
      prose: 2000,
      code: 3000,
      configuration: 1000,
      documentation: 2000,
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockLogger = {
      info: jest.fn(),
      error: jest.fn(),
      warn: jest.fn(),
      debug: jest.fn(),
      log: jest.fn(),
      child: jest.fn().mockReturnThis(),
      setContext: jest.fn(),
    } as unknown as BasePinoLogger;
    configService = {
      getEnhancementConfig: jest.fn().mockReturnValue(ENHANCEMENT_CONFIG),
      getEnrichmentConfig: jest.fn().mockReturnValue({
        enabled: false,
        apiKey: null,
        llmUrl: null,
        llmModel: null,
        maxConcurrency: 1,
        timeoutMs: 15000,
        docMaxTokens: 16000,
      }),
    } as unknown as ConfigurationService;
    service = new MastraChunkingService(configService, mockLogger);
  });

  test('should chunk UTF-8 rich content that exceeds request body limit and clamp to fit', async () => {
    // Construct content with Cyrillic characters that will generate chunks
    // exceeding the request body limit. Each Cyrillic character is 2 bytes in UTF-8.
    // Repeated paragraph will force multiple chunks, some of which will exceed
    // the maxChunkBytes limit and need clamping.
    const cyrillicParagraph =
      'Это тестовый абзац с кириллицей для проверки обработки UTF-8. ' +
      'Каждый символ занимает два байта в кодировке UTF-8. '.repeat(50);

    const content = cyrillicParagraph + cyrillicParagraph;

    // Verify content is large enough to generate multiple chunks and exceed limits
    const contentBytes = Buffer.byteLength(content, 'utf8');
    expect(contentBytes).toBeGreaterThan(ENHANCEMENT_CONFIG.serverRequestBodyLimit);

    // Mock MDocument to produce chunks that exceed maxChunkBytes, forcing clamping
    // Each chunk is 1500 characters (2-3KB) to exceed maxChunkBytes after wrapping
    const oversizedChunks = [];
    const chunkCharSize = 1500;
    for (let i = 0; i < content.length; i += chunkCharSize) {
      oversizedChunks.push({
        text: content.slice(i, i + chunkCharSize),
        metadata: { filePath: 'test.md' },
      });
    }

    mockedMDocument.fromMarkdown.mockReturnValue({
      chunkMarkdown: jest.fn(),
      getDocs: jest.fn().mockReturnValue(oversizedChunks),
      chunkRecursive: jest.fn(),
      chunkJSON: jest.fn(),
      chunkSentence: jest.fn(),
      extractMetadata: jest.fn().mockResolvedValue({
        getDocs: jest.fn().mockReturnValue(oversizedChunks),
      }),
    } as unknown as MDocument);

    // Run full chunking pipeline
    const result = await service.chunkFile(
      content,
      '/Volumes/Data/🌀My syncthings/Obsidian/olho/тест-файл.md',
      'obsidian_olho',
    );

    // Pipeline should succeed
    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks.length).toBeGreaterThan(0);

    // Verify each chunk fits within the request body limit when wrapped
    // in the rememberMemory envelope
    for (const chunk of chunks) {
      // Build the full request body to measure actual size
      const requestBody = service['buildRememberRequest'](chunk.text, {
        breadcrumb: chunk.breadcrumb,
        chunkIndex: chunk.chunkIndex,
      });
      const requestBodyBytes = Buffer.byteLength(requestBody, 'utf8');

      // Chunk must fit within the server request body limit
      expect(requestBodyBytes).toBeLessThanOrEqual(ENHANCEMENT_CONFIG.serverRequestBodyLimit);

      // Verify UTF-8 boundary integrity — no half-characters from bad truncation
      for (const char of chunk.text) {
        expect(char).not.toMatch(/[\uD800-\uDFFF]$/);
      }
    }

    // Verify clamped content is still valid UTF-8 by round-tripping through Buffer
    for (const chunk of chunks) {
      const encoded = Buffer.from(chunk.text, 'utf8');
      const decoded = encoded.toString('utf8');
      expect(decoded).toBe(chunk.text);
    }
  });

  test('should clamp chunks to fit request body via binary search', async () => {
    // Content that should exceed chunk size and trigger binary search clamping
    const cyrillicParagraph =
      'Это тестовый абзац с кириллицей для проверки обработки UTF-8. ' +
      'Каждый символ занимает два байта в кодировке UTF-8. '.repeat(100);
    const content = cyrillicParagraph + cyrillicParagraph;

    // Mock MDocument to produce large chunks that exceed maxChunkBytes
    const largeChunks = [
      {
        text: content.slice(0, content.length / 2),
        metadata: { filePath: 'test.md' },
      },
      {
        text: content.slice(content.length / 2),
        metadata: { filePath: 'test.md' },
      },
    ];

    mockedMDocument.fromMarkdown.mockReturnValue({
      chunkMarkdown: jest.fn(),
      getDocs: jest.fn().mockReturnValue(largeChunks),
      chunkRecursive: jest.fn(),
      chunkJSON: jest.fn(),
      chunkSentence: jest.fn(),
      extractMetadata: jest.fn().mockResolvedValue({
        getDocs: jest.fn().mockReturnValue(largeChunks),
      }),
    } as unknown as MDocument);

    const result = await service.chunkFile(
      content,
      '/Volumes/Data/🌀My syncthings/Obsidian/olho/тест-файл.md',
      'obsidian_olho',
    );

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks.length).toBeGreaterThan(0);

    // Verify all chunks are valid UTF-8 and within request body limit
    for (const chunk of chunks) {
      const requestBody = service['buildRememberRequest'](chunk.text, {
        breadcrumb: chunk.breadcrumb,
        chunkIndex: chunk.chunkIndex,
      });
      const requestBodyBytes = Buffer.byteLength(requestBody, 'utf8');
      expect(requestBodyBytes).toBeLessThanOrEqual(ENHANCEMENT_CONFIG.serverRequestBodyLimit);
    }
  });
});