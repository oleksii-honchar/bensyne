import '@/utils/mastra-rag.test-utils';

import { LlmClientFactory } from '../../application/services/llm-client-factory';
import { FILE_ROLES } from '../../domain/content-chunk.entity';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { SOURCE_TYPES } from '../../infrastructure/config/source-types';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';

import { MDocument } from '@mastra/rag';
import {
  assertExtractedEnrichment,
  deriveSummaryMaxWords,
  ENRICHMENT_429_MAX_RETRIES,
  EnrichmentValidationError,
  MastraChunkingService,
  MAX_ENRICHMENT_KEYWORDS_LENGTH,
} from './mastra-chunking.service';

const mockedMDocument = MDocument as jest.Mocked<typeof MDocument>;

const mockCustomLlm = {} as never;
const mockedLlmClientFactory = LlmClientFactory as jest.Mocked<typeof LlmClientFactory>;

const createMockConfigService = (overrides?: {
  maxCharacters?: Record<string, number>;
  enrichmentEnabled?: boolean;
  enrichmentApiKey?: string | null;
  enrichmentLlmUrl?: string | null;
  docMaxTokens?: number;
  timeoutMs?: number;
}) => {
  return {
    getEnhancementConfig: jest.fn().mockReturnValue({
      maxCharacters: {
        prose: 200,
        code: 400,
        configuration: 300,
        documentation: 300,
        ...overrides?.maxCharacters,
      },
    }),
    getEnrichmentConfig: jest.fn().mockReturnValue({
      enabled: overrides?.enrichmentEnabled ?? true,
      apiKey: overrides?.enrichmentApiKey !== undefined ? overrides.enrichmentApiKey : 'test-key',
      llmUrl:
        overrides?.enrichmentLlmUrl !== undefined ? overrides.enrichmentLlmUrl : 'https://lite-llm.lan/v1',
      llmModel: 'puma-qwopus3.5-9b',
      maxConcurrency: 1,
      timeoutMs: overrides?.timeoutMs ?? 15000,
      docMaxTokens: overrides?.docMaxTokens ?? 16000,
    }),
  } as unknown as ConfigurationService;
};

describe('deriveSummaryMaxWords', () => {
  it.each([
    [16000, 80],
    [2000, 20],
    [4000, 20],
    [24000, 120],
    [1000, 20],
    [0, 20],
    [50000, 120],
  ])('docMaxTokens=%i maps to summaryMaxWords=%i', (docMaxTokens, expected) => {
    expect(deriveSummaryMaxWords(docMaxTokens)).toBe(expected);
  });

  it('always stays within [20, 120] and is an integer across a wide range of docMaxTokens', () => {
    for (let docMaxTokens = 0; docMaxTokens <= 100000; docMaxTokens += 137) {
      const summaryMaxWords = deriveSummaryMaxWords(docMaxTokens);
      expect(summaryMaxWords).toBeGreaterThanOrEqual(20);
      expect(summaryMaxWords).toBeLessThanOrEqual(120);
      expect(Number.isInteger(summaryMaxWords)).toBe(true);
    }
  });
});

describe('MastraChunkingService', () => {
  let service: MastraChunkingService;
  let configService: ConfigurationService;
  let mockLogger: BasePinoLogger;

  const createMockLogger = (): BasePinoLogger => ({
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
    log: jest.fn(),
    child: jest.fn().mockReturnThis(),
    setContext: jest.fn(),
  });

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(LlmClientFactory, 'createCustomLlm').mockReturnValue(mockCustomLlm);
    configService = createMockConfigService();
    mockLogger = createMockLogger();
    service = new MastraChunkingService(configService, mockLogger);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('determineStrategy', () => {
    describe('markdown files', () => {
      it('should return markdown chunker for .md files', () => {
        expect(service['determineStrategy']('README.md')).toBe('markdown');
      });

      it('should return markdown chunker for .mdx files', () => {
        expect(service['determineStrategy']('page.mdx')).toBe('markdown');
      });

      it('should return markdown chunker for .markdown files', () => {
        expect(service['determineStrategy']('notes.markdown')).toBe('markdown');
      });
    });

    describe('code files - recursive', () => {
      it.each([
        ['.ts'],
        ['.tsx'],
        ['.js'],
        ['.jsx'],
        ['.py'],
        ['.go'],
        ['.java'],
        ['.rs'],
        ['.cs'],
        ['.php'],
        ['.rb'],
        ['.swift'],
        ['.kt'],
        ['.scala'],
        ['.cpp'],
        ['.c'],
        ['.h'],
        ['.hpp'],
        ['.m'],
        ['.mm'],
        ['.ex'],
        ['.exs'],
        ['.hs'],
        ['.pl'],
        ['.r'],
        ['.lua'],
        ['.dart'],
        ['.groovy'],
      ])('should return recursive chunker for %s files', ext => {
        expect(service['determineStrategy'](`file${ext}`)).toBe('recursive');
      });
    });

    describe('config files - json', () => {
      it.each([['.json'], ['.yaml'], ['.yml'], ['.toml'], ['.xml'], ['.ini'], ['.cfg'], ['.conf']])(
        'should return json chunker for %s files',
        ext => {
          expect(service['determineStrategy'](`config${ext}`)).toBe('json');
        },
      );

      it('should return json chunker for .env files', () => {
        expect(service['determineStrategy']('.env')).toBe('json');
      });

      it('should return json chunker for .env.local files', () => {
        expect(service['determineStrategy']('.env.local')).toBe('json');
      });
    });

    describe('text files - sentence', () => {
      it('should return sentence chunker for .txt files', () => {
        expect(service['determineStrategy']('notes.txt')).toBe('sentence');
      });

      it('should return sentence chunker for .text files', () => {
        expect(service['determineStrategy']('doc.text')).toBe('sentence');
      });

      it('should return sentence chunker for .log files', () => {
        expect(service['determineStrategy']('app.log')).toBe('sentence');
      });
    });

    describe('html files', () => {
      it('should return markdown chunker for .html files', () => {
        expect(service['determineStrategy']('page.html')).toBe('markdown');
      });

      it('should return markdown chunker for .htm files', () => {
        expect(service['determineStrategy']('page.htm')).toBe('markdown');
      });
    });

    describe('fallback', () => {
      it('should return sentence chunker for unknown extensions', () => {
        expect(service['determineStrategy']('file.unknown')).toBe('sentence');
      });

      it('should return sentence chunker for files without extension', () => {
        expect(service['determineStrategy']('Dockerfile')).toBe('sentence');
      });
    });

    describe('case insensitivity', () => {
      it('should handle uppercase extensions', () => {
        expect(service['determineStrategy']('README.MD')).toBe('markdown');
      });

      it('should handle mixed case extensions', () => {
        expect(service['determineStrategy']('file.Ts')).toBe('recursive');
      });
    });
  });

  describe('determineDocumentType', () => {
    it('should return markdown for .md files', () => {
      expect(service['determineDocumentType']('README.md')).toBe('markdown');
    });

    it('should return json for .json files', () => {
      expect(service['determineDocumentType']('config.json')).toBe('json');
    });

    it('should return html for .html files', () => {
      expect(service['determineDocumentType']('page.html')).toBe('html');
    });

    it('should return text for unknown extensions', () => {
      expect(service['determineDocumentType']('file.xyz')).toBe('text');
    });
  });

  describe('determineFileRole', () => {
    it('should return CODE for code files', () => {
      expect(service['determineFileRole']('app.ts')).toBe(FILE_ROLES.CODE);
    });

    it('should return CONFIG for config files', () => {
      expect(service['determineFileRole']('package.json')).toBe(FILE_ROLES.CONFIG);
    });

    it('should return DOCS for markdown files', () => {
      expect(service['determineFileRole']('README.md')).toBe(FILE_ROLES.DOCS);
    });

    it('should return DOCS as default', () => {
      expect(service['determineFileRole']('unknown.xyz')).toBe(FILE_ROLES.DOCS);
    });
  });

  describe('maxCharacters config wiring', () => {
    it('should read maxCharacters from ConfigurationService', () => {
      expect(configService.getEnhancementConfig).not.toHaveBeenCalled();
      // Just verify config service is injected and accessible
      expect(service['configService']).toBe(configService);
    });

    it('should map FILE_ROLES.DOCS → prose maxCharacters (200)', () => {
      const maxChars = service['getMaxCharacters'](FILE_ROLES.DOCS);
      expect(maxChars).toBe(200);
    });

    it('should map FILE_ROLES.CODE → code maxCharacters (400)', () => {
      const maxChars = service['getMaxCharacters'](FILE_ROLES.CODE);
      expect(maxChars).toBe(400);
    });

    it('should map FILE_ROLES.CONFIG → configuration maxCharacters (300)', () => {
      const maxChars = service['getMaxCharacters'](FILE_ROLES.CONFIG);
      expect(maxChars).toBe(300);
    });

    it('should pass maxSize to chunkMarkdown based on fileRole', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockDoc.chunkMarkdown).toHaveBeenCalledWith(expect.objectContaining({ maxSize: 200 }));
    });

    it('should pass maxSize to chunkRecursive based on fileRole', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkRecursive: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('function test() {}', 'app.ts', 'test-source');

      expect(mockDoc.chunkRecursive).toHaveBeenCalledWith(expect.objectContaining({ maxSize: 400 }));
    });

    it('should pass maxSize and minSize to chunkJSON based on fileRole', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkJSON: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromJSON.mockReturnValue(mockDoc as never);

      await service.chunkFile('{"key": "value"}', 'config.json', 'test-source');

      expect(mockDoc.chunkJSON).toHaveBeenCalledWith(
        expect.objectContaining({
          maxSize: 300,
          minSize: expect.any(Number),
        }),
      );
    });

    it('should pass maxSize, minSize, targetSize to chunkSentence based on fileRole', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkSentence: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('First sentence. Second sentence.', 'notes.txt', 'test-source');

      expect(mockDoc.chunkSentence).toHaveBeenCalledWith(
        expect.objectContaining({
          maxSize: 200,
          minSize: expect.any(Number),
          targetSize: expect.any(Number),
        }),
      );
    });

    it('should use code maxCharacters (400) for code files with the recursive chunker', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkRecursive: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('const x = 1;', 'script.js', 'test-source');

      expect(mockDoc.chunkRecursive).toHaveBeenCalledWith(expect.objectContaining({ maxSize: 400 }));
    });

    it('should use custom maxCharacters when config is overridden', async () => {
      configService = createMockConfigService({ maxCharacters: { prose: 300, code: 500 } });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockDoc.chunkMarkdown).toHaveBeenCalledWith(expect.objectContaining({ maxSize: 300 }));
    });

    it('should not truncate chunks post-chunking — relies on Mastra size limits', async () => {
      const longText = 'A'.repeat(500);
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: longText, metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: longText, metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title\n' + longText, 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // No truncation — if Mastra returns a chunk > maxChars, we keep it as-is (oversized flag handled by Mastra)
      expect(chunks[0].text).toBe(longText);
    });
  });

  describe('chunkFile', () => {
    it('should return Result.ok with chunks for valid markdown content', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'Chunk 1 content', metadata: { enrichment: { title: 'Test', keywords: 'test,chunk' } } },
            { text: 'Chunk 2 content', metadata: { enrichment: { title: 'Test', keywords: 'test,chunk' } } },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'Chunk 1 content', metadata: { enrichment: { title: 'Test', keywords: 'test,chunk' } } },
          { text: 'Chunk 2 content', metadata: { enrichment: { title: 'Test', keywords: 'test,chunk' } } },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Test\n\nContent here.', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(2);
      expect(chunks[0].text).toBe('Chunk 1 content');
      expect(chunks[1].text).toBe('Chunk 2 content');
    });

    it('should use MDocument.fromMarkdown for markdown files', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(MDocument.fromMarkdown).toHaveBeenCalled();
      expect(MDocument.fromJSON).not.toHaveBeenCalled();
      expect(MDocument.fromText).not.toHaveBeenCalled();
      expect(MDocument.fromHTML).not.toHaveBeenCalled();
    });

    it('should use MDocument.fromJSON for json files', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromJSON.mockReturnValue(mockDoc as never);

      await service.chunkFile('{"key": "value"}', 'config.json', 'test-source');

      expect(MDocument.fromJSON).toHaveBeenCalled();
    });

    it('should use MDocument.fromHTML for html files', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromHTML.mockReturnValue(mockDoc as never);

      await service.chunkFile('<html><body>Test</body></html>', 'page.html', 'test-source');

      expect(MDocument.fromHTML).toHaveBeenCalled();
    });

    it('should use MDocument.fromText for unknown file types', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('plain text content', 'notes.txt', 'test-source');

      expect(MDocument.fromText).toHaveBeenCalled();
    });

    it('should call chunkMarkdown for the markdown chunker', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title\nContent', 'README.md', 'test-source');

      expect(mockDoc.chunkMarkdown).toHaveBeenCalled();
    });

    it('should call chunkRecursive for the recursive chunker', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkRecursive: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('function test() {}', 'app.ts', 'test-source');

      expect(mockDoc.chunkRecursive).toHaveBeenCalled();
    });

    it('should call chunkJSON for the json chunker', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkJSON: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromJSON.mockReturnValue(mockDoc as never);

      await service.chunkFile('{"key": "value"}', 'config.json', 'test-source');

      expect(mockDoc.chunkJSON).toHaveBeenCalled();
    });

    it('should call chunkSentence for the sentence chunker', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkSentence: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      await service.chunkFile('First sentence. Second sentence.', 'notes.txt', 'test-source');

      expect(mockDoc.chunkSentence).toHaveBeenCalled();
    });

    it('should call extractMetadata with schema-based extraction when enrichment is enabled', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest
            .fn()
            .mockReturnValue([{ text: 'content', metadata: { enrichment: { title: 'T', keywords: 'k' } } }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest
          .fn()
          .mockReturnValue([{ text: 'content', metadata: { enrichment: { title: 'T', keywords: 'k' } } }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockDoc.extractMetadata).toHaveBeenCalledWith({
        schema: expect.objectContaining({
          llm: mockCustomLlm,
          instructions: expect.any(String),
          metadataKey: 'enrichment',
        }),
      });
    });

    it('should map Mastra chunks to Chunk entities with correct properties', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'First chunk text', metadata: { title: 'My Title', keywords: 'test,important' } },
            { text: 'Second chunk text', metadata: { title: 'My Title', keywords: 'test,important' } },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'First chunk text', metadata: { title: 'My Title', keywords: 'test,important' } },
          { text: 'Second chunk text', metadata: { title: 'My Title', keywords: 'test,important' } },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile(
        '# My Title\n\nFirst paragraph.\n\nSecond paragraph.',
        'README.md',
        'test-source',
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(2);

      const firstChunk = chunks[0];
      expect(firstChunk.text).toBe('First chunk text');
      expect(firstChunk.chunkIndex).toBe(0);
      expect(firstChunk.totalChunks).toBe(2);
      expect(firstChunk.fileRole).toBe(FILE_ROLES.DOCS);
      expect(firstChunk.metadata).toBeDefined();
      expect(firstChunk.metadata?.filePath).toBe('README.md');
      expect(firstChunk.metadata?.sourceId).toBe('test-source');
      expect(firstChunk.importance).toBe(0.5);
      expect(firstChunk.tags).toEqual([]);
      expect(firstChunk.memoryBank).toBe('default');
    });

    it('should include enrichment metadata in Chunk metadata', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'Extracted Title', keywords: 'keyword1,keyword2' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: { enrichment: { title: 'Extracted Title', keywords: 'keyword1,keyword2' } },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Extracted Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('keyword1,keyword2');
    });

    it('should use correct fileRole for code files', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'code chunk', metadata: {} }]),
        }),
        chunkRecursive: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'code chunk', metadata: {} }]),
      };
      mockedMDocument.fromText.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('function test() {}', 'app.ts', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].fileRole).toBe(FILE_ROLES.CODE);
    });

    it('should use correct fileRole for config files', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'config chunk', metadata: {} }]),
        }),
        chunkJSON: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'config chunk', metadata: {} }]),
      };
      mockedMDocument.fromJSON.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('{"key": "value"}', 'config.json', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].fileRole).toBe(FILE_ROLES.CONFIG);
    });

    it('should return empty array for empty content', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toHaveLength(0);
    });

    it('should return Result.ko when MDocument creation throws', async () => {
      mockedMDocument.fromMarkdown.mockImplementation(() => {
        throw new Error('Invalid markdown');
      });

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toContain('Invalid markdown');
    });

    it('should return Result.ko when chunking throws', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(() => {
          throw new Error('Chunking failed');
        }),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toContain('Chunking failed');
    });

    it('should gracefully continue when extractMetadata throws', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn(() => {
          throw new Error('Metadata extraction failed');
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
    });

    it('should map chunks with sequential indices', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            { text: 'chunk1', metadata: {} },
            { text: 'chunk2', metadata: {} },
            { text: 'chunk3', metadata: {} },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'chunk1', metadata: {} },
          { text: 'chunk2', metadata: {} },
          { text: 'chunk3', metadata: {} },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].chunkIndex).toBe(0);
      expect(chunks[1].chunkIndex).toBe(1);
      expect(chunks[2].chunkIndex).toBe(2);
      expect(chunks[0].totalChunks).toBe(3);
      expect(chunks[1].totalChunks).toBe(3);
      expect(chunks[2].totalChunks).toBe(3);
    });

    it('should set breadcrumb from filePath', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'docs/guide.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].breadcrumb).toBe('docs/guide.md');
    });
  });

  describe('enrichment with custom LLM', () => {
    it('should call LlmClientFactory.createCustomLlm when enrichment is enabled with llmUrl and apiKey', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).toHaveBeenCalled();
    });

    it('should pass custom LLM to extractMetadata schema extraction', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest
            .fn()
            .mockReturnValue([{ text: 'content', metadata: { enrichment: { title: 'T', keywords: 'k' } } }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest
          .fn()
          .mockReturnValue([{ text: 'content', metadata: { enrichment: { title: 'T', keywords: 'k' } } }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const callArg = mockDoc.extractMetadata.mock.calls[0][0];
      expect(callArg.schema.llm).toBe(mockCustomLlm);
      expect(callArg.schema.instructions).toBe(
        `You must respond ONLY with valid JSON.

Extract the following fields from the document:
- title: A concise title describing the content
- keywords: At most 10 concise, comma-separated keywords
- summary: A concise whole-file summary of the document, at most 80 words

ALL THREE fields (title, keywords, summary) are REQUIRED. None may be omitted and none may be null.

Respond in this format:
{
  "title": "string",
  "keywords": "keyword1, keyword2, keyword3",
  "summary": "string"
}

Do not include any other text, explanations, or markdown formatting.`,
      );
      expect(callArg.schema.metadataKey).toBe('enrichment');
    });

    it('should NOT call LlmClientFactory when enrichment is disabled', async () => {
      configService = createMockConfigService({ enrichmentEnabled: false });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should NOT call LlmClientFactory when llmUrl is missing', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: null,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should NOT call LlmClientFactory when apiKey is missing', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: null,
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should NOT call LlmClientFactory when both apiKey and llmUrl are missing', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: null,
        enrichmentLlmUrl: null,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should catch extractMetadata error and log warning without throwing', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockRejectedValue(new Error('LLM unavailable')),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toHaveLength(1);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('[mastra-chunking:enrichment] ExtractMetadata failed'),
        expect.objectContaining({ error: 'LLM unavailable' }),
      );
    });

    it('should skip extractMetadata when LlmClientFactory returns null', async () => {
      jest.spyOn(LlmClientFactory, 'createCustomLlm').mockReturnValue(null);
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(LlmClientFactory.createCustomLlm).toHaveBeenCalled();
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should attach enrichment metadata from chunk.metadata.enrichment to chunks', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'Enriched Title', keywords: 'enriched,keywords' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: { enrichment: { title: 'Enriched Title', keywords: 'enriched,keywords' } },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Enriched Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('enriched,keywords');
    });

    it('should include summary in the enrichment schema passed to extractMetadata', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: {
                enrichment: { title: 'T', keywords: 'k', summary: 'Whole-file summary of the document.' },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: {
              enrichment: { title: 'T', keywords: 'k', summary: 'Whole-file summary of the document.' },
            },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const callArg = mockDoc.extractMetadata.mock.calls[0][0];
      // The schema must expose `summary` so the LLM output carries it end-to-end
      expect(callArg.schema.schema.shape.summary).toBeDefined();
      const parsed = callArg.schema.schema.safeParse({
        title: 'T',
        keywords: 'k',
        summary: 'Whole-file summary of the document.',
      });
      expect(parsed.success).toBe(true);
      expect(parsed.data.summary).toBe('Whole-file summary of the document.');
    });

    it('should include the exact derived word cap in the extraction instructions (default 16000 → 80 words)', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const callArg = mockDoc.extractMetadata.mock.calls[0][0];
      expect(callArg.schema.instructions).toContain('at most 80 words');
    });

    it.each([
      [2000, 'at most 20 words'],
      [24000, 'at most 120 words'],
    ])(
      'should instruct the LLM with the derived cap for docMaxTokens=%i',
      async (docMaxTokens, expectedPhrase) => {
        configService = createMockConfigService({
          enrichmentEnabled: true,
          enrichmentApiKey: 'test-key',
          enrichmentLlmUrl: 'https://lite-llm.lan/v1',
          docMaxTokens,
        });
        service = new MastraChunkingService(configService, mockLogger);

        const mockDoc = {
          extractMetadata: jest.fn().mockResolvedValue({
            getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
          }),
          chunkMarkdown: jest.fn(),
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        };
        mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

        await service.chunkFile('# Title', 'README.md', 'test-source');

        const callArg = mockDoc.extractMetadata.mock.calls[0][0];
        expect(callArg.schema.instructions).toContain(expectedPhrase);
      },
    );

    it('should include summary in the "Respond in this format" JSON example AND list all three required fields', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const instructions = mockDoc.extractMetadata.mock.calls[0][0].schema.instructions;

      // The format example must include summary so the LLM emits it (schema requires it)
      expect(instructions).toContain('"summary": "string"');
      // All three fields are described in the field list
      expect(instructions).toContain('- title:');
      expect(instructions).toContain('- keywords:');
      expect(instructions).toContain('- summary:');
      // The prompt explicitly requires all three fields and forbids null/omission
      expect(instructions).toContain('ALL THREE fields (title, keywords, summary) are REQUIRED');
      expect(instructions).toMatch(/REQUIRED/i);
      expect(instructions).toMatch(/none may be omitted/i);
      expect(instructions).toMatch(/none may be null/i);
    });

    it('should constrain keywords to at most 10 concise, comma-separated keywords in the instructions', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const instructions = mockDoc.extractMetadata.mock.calls[0][0].schema.instructions;
      expect(instructions).toMatch(/at most 10/i);
      expect(instructions).toContain('comma-separated keywords');
    });

    it('should map enrichment metadata (mastraDocTitle, mastraDocKeywords, mastraDocSummary) onto chunks when LLM returns all three fields', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const wholeFileSummary = 'A concise whole-file summary of the document.';
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: {
                enrichment: {
                  title: 'Extracted Title',
                  keywords: 'one,two,three',
                  summary: wholeFileSummary,
                },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: {
              enrichment: {
                title: 'Extracted Title',
                keywords: 'one,two,three',
                summary: wholeFileSummary,
              },
            },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Extracted Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('one,two,three');
      expect(chunk.metadata?.mastraDocSummary).toBe(wholeFileSummary);
    });

    it('should abort enrichment within the configured timeoutMs when the LLM never resolves', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
        timeoutMs: 50,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const hungDoc = {
        extractMetadata: jest.fn(() => new Promise<never>(() => undefined)),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(hungDoc as never);

      const startedAt = Date.now();
      const result = await service.chunkFile('# Title', 'README.md', 'test-source');
      const elapsedMs = Date.now() - startedAt;

      expect(result.isOk()).toBe(true);
      // The hung generation must not block the file — we return within a sane bound
      expect(elapsedMs).toBeLessThan(2000);
      // The file is processed un-enriched (enrichment aborted)
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBeUndefined();
    });

    it('should truncate over-long/repeated keywords so mapped chunk metadata does not grow unbounded', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const runawayKeywords = 'kw,'.repeat(100_000);
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: {
                enrichment: { title: 'T', keywords: runawayKeywords, summary: 'S' },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: {
              enrichment: { title: 'T', keywords: runawayKeywords, summary: 'S' },
            },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const keywords = result.getValue()[0].metadata?.mastraDocKeywords;
      expect(typeof keywords).toBe('string');
      expect((keywords as string).length).toBeLessThanOrEqual(MAX_ENRICHMENT_KEYWORDS_LENGTH);
      expect((keywords as string).length).toBeLessThan(runawayKeywords.length);
    });

    it('should pass a derived maxOutputTokens bound into LlmClientFactory for the enrichment LLM', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
        docMaxTokens: 16000,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const factoryArg = (LlmClientFactory.createCustomLlm as jest.Mock).mock.calls[0][0];
      expect(factoryArg.maxOutputTokens).toBe(1024);
    });
  });

  describe('enrichment corrective retry', () => {
    const setupDoc = (
      extractMetadataImpl: jest.Mock,
      getDocsResult: { text: string; metadata: Record<string, unknown> }[],
    ) => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: extractMetadataImpl,
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue(getDocsResult),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);
      return mockDoc;
    };

    it('should retry extractMetadata ONCE with the corrective instruction when the first attempt RESOLVES empty (real Mastra contract), and use the second attempt output', async () => {
      const enrichedChunk = {
        text: 'content',
        metadata: {
          enrichment: { title: 'Retried Title', keywords: 'retry,works', summary: 'Retry summary.' },
        },
      };
      const mockDoc = setupDoc(
        jest
          .fn()
          // Real Mastra contract (R6): SchemaExtractor swallows validation errors and
          // RESOLVES with an empty/un-enriched doc — it never rejects on schema failure.
          .mockResolvedValueOnce({
            getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
          })
          .mockResolvedValueOnce({ getDocs: jest.fn().mockReturnValue([enrichedChunk]) }),
        [enrichedChunk],
      );

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      // Behavior: the second attempt's output is the one used — chunks carry enrichment metadata
      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Retried Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('retry,works');
      expect(chunk.metadata?.mastraDocSummary).toBe('Retry summary.');

      // Exactly one retry: two calls total, no more
      expect(mockDoc.extractMetadata).toHaveBeenCalledTimes(2);

      // First attempt uses the base prompt; the retry carries the corrective instruction
      const firstInstructions = mockDoc.extractMetadata.mock.calls[0][0].schema.instructions;
      const secondInstructions = mockDoc.extractMetadata.mock.calls[1][0].schema.instructions;
      expect(firstInstructions).not.toContain('previous response failed validation');
      expect(secondInstructions).toContain('previous response failed validation');
    });

    it('should return Result.ok un-enriched chunks when BOTH attempts RESOLVE empty — no throw, file processing continues', async () => {
      const mockDoc = setupDoc(
        jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        [{ text: 'content', metadata: {} }],
      );

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toHaveLength(1);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBeUndefined();

      // Exactly one corrective retry — no unbounded loop (at most 2 LLM calls per chunk)
      expect(mockDoc.extractMetadata).toHaveBeenCalledTimes(2);

      // Secondary: the both-fail WARN surfaces the validation error message
      // (primary behavioral checks above: Result.ok, chunk un-enriched, loop continues).
      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] ExtractMetadata failed',
        expect.objectContaining({ error: expect.stringContaining('missing or invalid fields') }),
      );
    });

    it('should not retry when the first enrichment attempt succeeds', async () => {
      const mockDoc = setupDoc(
        jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: 'S' } },
            },
          ]),
        }),
        [
          {
            text: 'content',
            metadata: { enrichment: { title: 'T', keywords: 'k', summary: 'S' } },
          },
        ],
      );

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(mockDoc.extractMetadata).toHaveBeenCalledTimes(1);
      const instructions = mockDoc.extractMetadata.mock.calls[0][0].schema.instructions;
      expect(instructions).not.toContain('previous response failed validation');
    });
  });

  describe('assertExtractedEnrichment (DEC-0069 — post-validate the RESOLVED result)', () => {
    const docWithEnrichment = (enrichment: unknown): MDocument =>
      ({
        getDocs: () => [{ text: 'content', metadata: { enrichment } }],
      }) as unknown as MDocument;

    const docWithNoEnrichment = (): MDocument =>
      ({ getDocs: () => [{ text: 'content', metadata: {} }] }) as unknown as MDocument;

    const expectMissingFields = (doc: MDocument, expected: string[]): void => {
      expect(() => assertExtractedEnrichment(doc)).toThrow(EnrichmentValidationError);
      try {
        assertExtractedEnrichment(doc);
        throw new Error('expected assertExtractedEnrichment to throw');
      } catch (error) {
        expect((error as EnrichmentValidationError).missingFields).toEqual(expected);
      }
    };

    it('does not throw when enrichment is an object with string title/keywords/summary', () => {
      expect(() =>
        assertExtractedEnrichment(docWithEnrichment({ title: 'T', keywords: 'k', summary: 'S' })),
      ).not.toThrow();
    });

    it('throws with missingFields ["enrichment"] when the enrichment object is missing', () => {
      expectMissingFields(docWithNoEnrichment(), ['enrichment']);
    });

    it('throws with missingFields ["enrichment"] when the document has no docs at all', () => {
      expectMissingFields({ getDocs: () => [] } as unknown as MDocument, ['enrichment']);
    });

    it('throws with missingFields ["enrichment"] when enrichment is not an object (string)', () => {
      expectMissingFields(docWithEnrichment('not-an-object'), ['enrichment']);
    });

    it('throws with missingFields ["enrichment"] when enrichment is an array', () => {
      expectMissingFields(docWithEnrichment([]), ['enrichment']);
    });

    it('throws with missingFields ["title"] when title is missing', () => {
      expectMissingFields(docWithEnrichment({ keywords: 'k', summary: 'S' }), ['title']);
    });

    it('throws with missingFields ["keywords"] when keywords is missing', () => {
      expectMissingFields(docWithEnrichment({ title: 'T', summary: 'S' }), ['keywords']);
    });

    it('throws with missingFields ["summary"] when summary is missing', () => {
      expectMissingFields(docWithEnrichment({ title: 'T', keywords: 'k' }), ['summary']);
    });

    it('throws with missingFields ["title"] when a field value is not a string', () => {
      expectMissingFields(docWithEnrichment({ title: 42, keywords: 'k', summary: 'S' }), ['title']);
    });

    it('lists every missing/invalid field when the enrichment object is empty', () => {
      expectMissingFields(docWithEnrichment({}), ['title', 'keywords', 'summary']);
    });

    it('exposes the missing fields via the error message (surfaces in the ExtractMetadata failed WARN)', () => {
      try {
        assertExtractedEnrichment(docWithNoEnrichment());
        throw new Error('expected assertExtractedEnrichment to throw');
      } catch (error) {
        expect((error as Error).message).toContain('missing or invalid fields');
      }
    });
  });

  describe('enrichment per-chunk serialization (Task 9 — concurrency 1)', () => {
    const chunkTexts = ['Chunk A', 'Chunk B', 'Chunk C'];

    const enableEnrichment = () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);
    };

    const flushMicrotasks = async (): Promise<void> => {
      for (let i = 0; i < 10; i += 1) {
        await Promise.resolve();
      }
    };

    /**
     * Mock extractMetadata that records how many calls are in flight at any
     * moment and defers settlement until the test resolves each call.
     */
    const buildConcurrencyTrackingDoc = () => {
      let active = 0;
      let maxConcurrency = 0;
      const deferreds: { resolve: (value: unknown) => void }[] = [];

      const extractMetadata = jest.fn(
        () =>
          new Promise(resolve => {
            active += 1;
            maxConcurrency = Math.max(maxConcurrency, active);
            deferreds.push({
              resolve: value => {
                active -= 1;
                resolve(value);
              },
            });
          }),
      );

      const doc = {
        extractMetadata,
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue(chunkTexts.map(text => ({ text, metadata: {} }))),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      return { doc, deferreds, maxConcurrency: () => maxConcurrency };
    };

    it('invokes the enrichment LLM exactly N times for N chunks and never has more than 1 call in flight', async () => {
      enableEnrichment();
      const { doc, deferreds, maxConcurrency } = buildConcurrencyTrackingDoc();

      const pending = service.chunkFile('# Title\n\nA\n\nB\n\nC', 'README.md', 'test-source');

      for (let i = 0; i < chunkTexts.length; i += 1) {
        await flushMicrotasks();
        // While chunk i is still pending, the service must not have started chunk i+1.
        expect(doc.extractMetadata).toHaveBeenCalledTimes(i + 1);
        expect(maxConcurrency()).toBe(1);
        deferreds[i].resolve({
          getDocs: jest.fn().mockReturnValue([
            {
              text: chunkTexts[i],
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: 'S' } },
            },
          ]),
        });
      }

      const result = await pending;

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toHaveLength(3);
      expect(doc.extractMetadata).toHaveBeenCalledTimes(3);
      expect(maxConcurrency()).toBe(1);
    });

    it('maps enrichment metadata onto EACH chunk from its own per-chunk enrichment call', async () => {
      enableEnrichment();

      const enrichments = [
        { title: 'Title A', keywords: 'ka', summary: 'Summary A' },
        { title: 'Title B', keywords: 'kb', summary: 'Summary B' },
        { title: 'Title C', keywords: 'kc', summary: 'Summary C' },
      ];

      let callIndex = 0;
      const doc = {
        extractMetadata: jest.fn().mockImplementation(() => {
          const enrichment = enrichments[callIndex];
          callIndex += 1;
          return Promise.resolve({
            getDocs: jest.fn().mockReturnValue([{ text: 'chunk', metadata: { enrichment } }]),
          });
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue(chunkTexts.map(text => ({ text, metadata: {} }))),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB\n\nC', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(3);
      chunks.forEach((chunk, i) => {
        expect(chunk.metadata?.mastraDocTitle).toBe(enrichments[i].title);
        expect(chunk.metadata?.mastraDocKeywords).toBe(enrichments[i].keywords);
        expect(chunk.metadata?.mastraDocSummary).toBe(enrichments[i].summary);
      });
    });

    it('applies the corrective retry per chunk — a failing first attempt for a chunk triggers exactly one retry for that chunk', async () => {
      enableEnrichment();

      const enrichments = [
        { title: 'Retried A', keywords: 'ka', summary: 'Summary A' },
        { title: 'Title B', keywords: 'kb', summary: 'Summary B' },
      ];

      let callIndex = 0;
      const doc = {
        extractMetadata: jest.fn().mockImplementation(() => {
          const current = callIndex;
          callIndex += 1;
          if (current === 0) {
            return Promise.reject(new Error('summary: expected string, received undefined'));
          }
          const enrichment = enrichments[current - 1];
          return Promise.resolve({
            getDocs: jest.fn().mockReturnValue([{ text: 'chunk', metadata: { enrichment } }]),
          });
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'Chunk A', metadata: {} },
          { text: 'Chunk B', metadata: {} },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks[0].metadata?.mastraDocTitle).toBe('Retried A');
      expect(chunks[1].metadata?.mastraDocTitle).toBe('Title B');
      // Chunk A: attempt + one retry = 2 calls; Chunk B: 1 call.
      expect(doc.extractMetadata).toHaveBeenCalledTimes(3);
      const correctiveCalls = doc.extractMetadata.mock.calls
        .map((call, idx) => ({ idx, instructions: call[0].schema.instructions as string }))
        .filter(call => call.instructions.includes('previous response failed validation'))
        .map(call => call.idx);
      expect(correctiveCalls).toEqual([1]);
    });
  });

  describe('enrichment 429 backoff retry (Task 10 — bounded backoff on transient 429s)', () => {
    let sleepMock: jest.Mock;

    const enableEnrichment = (): jest.Mock => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      sleepMock = jest.fn().mockResolvedValue(undefined);
      service = new MastraChunkingService(configService, mockLogger, sleepMock);
      return sleepMock;
    };

    const rateLimitError = (): Error =>
      Object.assign(new Error('429 Too Many Requests'), { statusCode: 429 });

    it('retries a 429 with backoff and, on success, the chunk carries enrichment metadata', async () => {
      const sleepMock = enableEnrichment();

      const enrichedChunk = {
        text: 'Chunk A',
        metadata: { enrichment: { title: 'Title A', keywords: 'ka', summary: 'Summary A' } },
      };
      const doc = {
        extractMetadata: jest
          .fn()
          .mockRejectedValueOnce(rateLimitError())
          .mockResolvedValueOnce({ getDocs: jest.fn().mockReturnValue([enrichedChunk]) }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'Chunk A', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Title A');
      expect(chunk.metadata?.mastraDocKeywords).toBe('ka');
      expect(chunk.metadata?.mastraDocSummary).toBe('Summary A');

      // The 429 was retried with the first backoff step (250ms) before success.
      expect(sleepMock).toHaveBeenCalledTimes(1);
      expect(sleepMock).toHaveBeenCalledWith(250);
      // 1 initial attempt + 1 backoff retry.
      expect(doc.extractMetadata).toHaveBeenCalledTimes(2);

      // The backoff retry is a plain re-attempt of the same instructions — not the corrective retry.
      const secondInstructions = doc.extractMetadata.mock.calls[1][0].schema.instructions;
      expect(secondInstructions).not.toContain('previous response failed validation');
    });

    it('stores the chunk un-enriched when every backoff retry 429s — no throw, no unbounded loop', async () => {
      const sleepMock = enableEnrichment();

      const doc = {
        extractMetadata: jest.fn().mockRejectedValue(rateLimitError()),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'Chunk A', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBeUndefined();
      expect(chunk.metadata?.mastraDocKeywords).toBeUndefined();

      // Bounded: 1 initial attempt + ENRICHMENT_429_MAX_RETRIES backoff retries — never more.
      expect(doc.extractMetadata).toHaveBeenCalledTimes(1 + ENRICHMENT_429_MAX_RETRIES);
      expect(doc.extractMetadata).toHaveBeenCalledTimes(3);
      // Backoff stepped 250ms then 500ms.
      expect(sleepMock.mock.calls.map(call => call[0])).toEqual([250, 500]);
    });

    it('does NOT backoff-retry validation errors — they fall straight through to the corrective retry', async () => {
      const sleepMock = enableEnrichment();

      const correctedChunk = {
        text: 'Chunk A',
        metadata: {
          enrichment: { title: 'Corrected Title', keywords: 'kc', summary: 'Corrected summary.' },
        },
      };
      const doc = {
        extractMetadata: jest
          .fn()
          .mockRejectedValueOnce(new Error('summary: expected string, received undefined'))
          .mockResolvedValueOnce({ getDocs: jest.fn().mockReturnValue([correctedChunk]) }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'Chunk A', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBe('Corrected Title');

      // No backoff sleep at all — the validation error goes straight to the corrective retry.
      expect(sleepMock).not.toHaveBeenCalled();
      expect(doc.extractMetadata).toHaveBeenCalledTimes(2);
      const secondInstructions = doc.extractMetadata.mock.calls[1][0].schema.instructions;
      expect(secondInstructions).toContain('previous response failed validation');
    });

    it('keeps total LLM calls per chunk within the bound (429 backoff + corrective retry <= 3)', async () => {
      const sleepMock = enableEnrichment();

      let callIndex = 0;
      const doc = {
        extractMetadata: jest.fn().mockImplementation(() => {
          const current = callIndex;
          callIndex += 1;
          if (current === 0) {
            // Initial attempt: transient 429 → backoff retry.
            return Promise.reject(rateLimitError());
          }
          if (current === 1) {
            // Backoff retry: validation error (NOT a 429) → corrective retry.
            return Promise.reject(new Error('summary: expected string, received undefined'));
          }
          // Corrective retry succeeds.
          return Promise.resolve({
            getDocs: jest.fn().mockReturnValue([
              {
                text: 'Chunk A',
                metadata: { enrichment: { title: 'Recovered', keywords: 'k', summary: 'S' } },
              },
            ]),
          });
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'Chunk A', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBe('Recovered');
      // Initial 429 + backoff retry (validation) + corrective retry = 3 calls — the bound.
      expect(doc.extractMetadata).toHaveBeenCalledTimes(3);
      expect(doc.extractMetadata).toHaveBeenCalledTimes(1 + ENRICHMENT_429_MAX_RETRIES);
      // Only the 429 triggered a backoff; the validation error went to the corrective retry.
      expect(sleepMock).toHaveBeenCalledTimes(1);
      expect(sleepMock).toHaveBeenCalledWith(250);
    });

    it('keeps a chunk whose LLM calls all 429 un-enriched without aborting the remaining chunks', async () => {
      const sleepMock = enableEnrichment();

      let callIndex = 0;
      const doc = {
        extractMetadata: jest.fn().mockImplementation(() => {
          const current = callIndex;
          callIndex += 1;
          if (current < 3) {
            // Chunk A: initial attempt + 2 backoff retries all 429 (Task 10).
            return Promise.reject(rateLimitError());
          }
          return Promise.resolve({
            getDocs: jest.fn().mockReturnValue([
              {
                text: 'Chunk B',
                metadata: { enrichment: { title: 'Title B', keywords: 'kb', summary: 'Summary B' } },
              },
            ]),
          });
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'Chunk A', metadata: {} },
          { text: 'Chunk B', metadata: {} },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(doc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(2);
      expect(chunks[0].metadata?.mastraDocTitle).toBeUndefined();
      expect(chunks[1].metadata?.mastraDocTitle).toBe('Title B');
      // Chunk A: initial + 2 backoff retries = 3 calls; Chunk B: 1 call.
      expect(doc.extractMetadata).toHaveBeenCalledTimes(4);
      // Chunk A's retries stepped 250ms then 500ms; Chunk B needed no backoff.
      expect(sleepMock.mock.calls.map(call => call[0])).toEqual([250, 500]);
    });
  });

  describe('mapToDomainChunks — mastraDocSummary stamping', () => {
    it('should stamp mastraDocSummary on EVERY chunk of a multi-chunk document when enrichment returns a summary', async () => {
      const wholeFileSummary = 'A concise whole-file summary of the multi-chunk document.';
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'Chunk 1 content',
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
            },
            {
              text: 'Chunk 2 content',
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
            },
            {
              text: 'Chunk 3 content',
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'Chunk 1 content',
            metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
          },
          {
            text: 'Chunk 2 content',
            metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
          },
          {
            text: 'Chunk 3 content',
            metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB\n\nC', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(3);
      for (const chunk of chunks) {
        expect(chunk.metadata?.mastraDocSummary).toBe(wholeFileSummary);
      }
    });

    it('should NOT stamp mastraDocSummary when enrichment summary is absent', async () => {
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'Extracted Title', keywords: 'keyword1,keyword2' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: { enrichment: { title: 'Extracted Title', keywords: 'keyword1,keyword2' } },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocSummary).toBeUndefined();
      expect(Object.prototype.hasOwnProperty.call(chunk.metadata ?? {}, 'mastraDocSummary')).toBe(false);
    });

    it('should NOT stamp mastraDocSummary on chunks produced without Mastra enrichment (enrichment disabled)', async () => {
      configService = createMockConfigService({ enrichmentEnabled: false });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocSummary).toBeUndefined();
      expect(Object.prototype.hasOwnProperty.call(chunk.metadata ?? {}, 'mastraDocSummary')).toBe(false);
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
    });

    it('should stamp mastraDocSummary on a single-chunk document (uniformity, not first-chunk-only)', async () => {
      const wholeFileSummary = 'A concise whole-file summary of a single-chunk document.';
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: { enrichment: { title: 'T', keywords: 'k', summary: wholeFileSummary } },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocSummary).toBe(wholeFileSummary);
    });
  });

  describe('enrichment logging', () => {
    it('should log enrichment attempt info when config has enabled+llmUrl+apiKey', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Attempting enrichment',
        expect.objectContaining({
          enabled: true,
          llmUrl: 'present',
          apiKey: 'present',
          filePath: 'README.md',
        }),
      );
    });

    it('should log enrichment skipped info when enabled=false', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: false,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Skipped',
        expect.objectContaining({
          reason: 'enabled=false',
          filePath: 'README.md',
        }),
      );
    });

    it('should log enrichment skipped info when apiKey=null', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: null,
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Skipped',
        expect.objectContaining({
          reason: 'missing apiKey',
          filePath: 'README.md',
        }),
      );
    });

    it('should log enrichment skipped info when llmUrl=null', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: null,
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Skipped',
        expect.objectContaining({
          reason: 'missing llmUrl',
          filePath: 'README.md',
        }),
      );
    });

    it('should log enrichment failure warn when extractMetadata throws', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockRejectedValue(new Error('LLM unavailable')),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] ExtractMetadata failed',
        expect.objectContaining({
          error: 'LLM unavailable',
          filePath: 'README.md',
        }),
      );
    });

    it('should log enrichment success info with metadata key indicators when extractMetadata succeeds', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: {
                enrichment: {
                  title: 'Enriched Title',
                  keywords: 'enriched,keywords',
                  summary: 'Whole-file summary of the document.',
                },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: {
              enrichment: {
                title: 'Enriched Title',
                keywords: 'enriched,keywords',
                summary: 'Whole-file summary of the document.',
              },
            },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=1, failed=0',
        expect.objectContaining({
          totalChunks: 1,
          enrichedCount: 1,
          failedCount: 0,
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
          filePath: 'README.md',
        }),
      );
    });

    it('should log hasSummary=true in the Extracted metadata payload when enrichment includes a summary', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const enrichedDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: {
                enrichment: { title: 'T', keywords: 'k', summary: 'Whole-file summary.' },
              },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          {
            text: 'content',
            metadata: {
              enrichment: { title: 'T', keywords: 'k', summary: 'Whole-file summary.' },
            },
          },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=1, failed=0',
        expect.objectContaining({
          totalChunks: 1,
          enrichedCount: 1,
          failedCount: 0,
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
          filePath: 'README.md',
        }),
      );
    });

    it('should log aggregate has* false when every chunk fails enrichment validation (summary required)', async () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      // Real Mastra contract (R6): extractMetadata RESOLVES with a partial
      // enrichment object (missing summary). `assertExtractedEnrichment` treats it
      // as invalid on BOTH attempts, so the chunk is left un-enriched.
      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([
            {
              text: 'content',
              metadata: { enrichment: { title: 'T', keywords: 'k' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      // No chunk is enriched, so the aggregate has* flags are all false.
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=0, failed=1',
        expect.objectContaining({
          totalChunks: 1,
          enrichedCount: 0,
          failedCount: 1,
          hasTitle: false,
          hasKeywords: false,
          hasSummary: false,
          filePath: 'README.md',
        }),
      );
      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Some chunks failed enrichment',
        expect.objectContaining({
          failedCount: 1,
          totalChunks: 1,
          filePath: 'README.md',
          firstFailureReason: expect.stringContaining('missing or invalid fields'),
        }),
      );
    });
  });

  describe('enrichment per-chunk observability + file-level aggregate (DEC-0068)', () => {
    const enableEnrichment = (): void => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);
    };

    const enrichedChunk = (
      title: string,
      keywords = 'k',
      summary = 'S',
    ): { text: string; metadata: Record<string, unknown> } => ({
      text: 'content',
      metadata: { enrichment: { title, keywords, summary } },
    });

    it('emits Chunk enriched INFO (attempts=1, 0-based chunkIndex) and all-enriched aggregate without a failure WARN', async () => {
      enableEnrichment();

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([enrichedChunk('T')]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([enrichedChunk('T')]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      // Behavioral: the enriched chunk carries the enrichment metadata.
      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('T');
      expect(chunk.metadata?.mastraDocKeywords).toBe('k');
      expect(chunk.metadata?.mastraDocSummary).toBe('S');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Chunk enriched',
        expect.objectContaining({
          chunkIndex: 0,
          chunkCount: 1,
          filePath: 'README.md',
          attempts: 1,
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
        }),
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=1, failed=0',
        expect.objectContaining({
          totalChunks: 1,
          enrichedCount: 1,
          failedCount: 0,
          filePath: 'README.md',
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
        }),
      );

      expect(mockLogger.warn).not.toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Some chunks failed enrichment',
        expect.anything(),
      );
    });

    it('emits Chunk enriched INFO with attempts=2 when the corrective retry succeeds', async () => {
      enableEnrichment();

      const mockDoc = {
        extractMetadata: jest
          .fn()
          .mockResolvedValueOnce({
            getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
          })
          .mockResolvedValueOnce({ getDocs: jest.fn().mockReturnValue([enrichedChunk('Retried')]) }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([enrichedChunk('Retried')]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      // Behavioral: corrective attempt output lands in chunk metadata, bounded to 2 calls.
      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBe('Retried');
      expect(mockDoc.extractMetadata).toHaveBeenCalledTimes(2);

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Chunk enriched',
        expect.objectContaining({
          chunkIndex: 0,
          chunkCount: 1,
          filePath: 'README.md',
          attempts: 2,
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
        }),
      );

      // The chunk still counts as enriched in the aggregate (no corrective-fail WARN).
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=1, failed=0',
        expect.objectContaining({ totalChunks: 1, enrichedCount: 1, failedCount: 0 }),
      );
    });

    it('emits WARN ExtractMetadata failed with chunkIndex/chunkCount/attempts/error/stack when both attempts fail', async () => {
      enableEnrichment();

      const mockDoc = {
        extractMetadata: jest.fn().mockRejectedValue(new Error('LLM unavailable')),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      // Behavioral: chunk un-enriched, Result.ok, loop continues.
      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBeUndefined();

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] ExtractMetadata failed',
        expect.objectContaining({
          chunkIndex: 0,
          chunkCount: 1,
          filePath: 'README.md',
          attempts: 2,
          error: 'LLM unavailable',
        }),
      );
      const warnCall = (mockLogger.warn as jest.Mock).mock.calls.find(
        (call: unknown[]) => call[0] === '[mastra-chunking:enrichment] ExtractMetadata failed',
      );
      expect(typeof (warnCall?.[1] as { stack?: unknown }).stack).toBe('string');

      // File-level aggregate reflects the failure and surfaces the reason.
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=0, failed=1',
        expect.objectContaining({
          totalChunks: 1,
          enrichedCount: 0,
          failedCount: 1,
          filePath: 'README.md',
          hasTitle: false,
          hasKeywords: false,
          hasSummary: false,
        }),
      );
      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Some chunks failed enrichment',
        expect.objectContaining({
          failedCount: 1,
          totalChunks: 1,
          filePath: 'README.md',
          firstFailureReason: 'LLM unavailable',
        }),
      );
    });

    it('emits WARN Rate limit retries exhausted with chunkIndex/chunkCount/error/retries when 429s are exhausted', async () => {
      const sleepMock = jest.fn().mockResolvedValue(undefined);
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger, sleepMock);

      const rateLimitError = (): Error =>
        Object.assign(new Error('429 Too Many Requests'), { statusCode: 429 });
      const mockDoc = {
        extractMetadata: jest.fn().mockRejectedValue(rateLimitError()),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      // Behavioral: chunk un-enriched, bounded to 1 initial + ENRICHMENT_429_MAX_RETRIES calls.
      expect(result.isOk()).toBe(true);
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBeUndefined();
      expect(mockDoc.extractMetadata).toHaveBeenCalledTimes(1 + ENRICHMENT_429_MAX_RETRIES);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Rate limit retries exhausted',
        expect.objectContaining({
          chunkIndex: 0,
          chunkCount: 1,
          filePath: 'README.md',
          error: '429 Too Many Requests',
          retries: ENRICHMENT_429_MAX_RETRIES,
        }),
      );
    });

    it('emits file-level aggregate enriched=1, failed=1 with has* true from the enriched chunk plus the failure WARN', async () => {
      enableEnrichment();

      const mockDoc = {
        extractMetadata: jest
          .fn()
          .mockResolvedValueOnce({ getDocs: jest.fn().mockReturnValue([enrichedChunk('Title A')]) })
          .mockRejectedValueOnce(new Error('second chunk boom'))
          .mockRejectedValueOnce(new Error('second chunk boom')),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'Chunk A', metadata: {} },
          { text: 'Chunk B', metadata: {} },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB', 'README.md', 'test-source');

      // Behavioral: chunk A enriched, chunk B un-enriched, both returned, Result.ok.
      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks).toHaveLength(2);
      expect(chunks[0].metadata?.mastraDocTitle).toBe('Title A');
      expect(chunks[1].metadata?.mastraDocTitle).toBeUndefined();

      // Per-chunk log uses 0-based chunkIndex and total chunk count.
      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Chunk enriched',
        expect.objectContaining({ chunkIndex: 0, chunkCount: 2, filePath: 'README.md', attempts: 1 }),
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=1, failed=1',
        expect.objectContaining({
          totalChunks: 2,
          enrichedCount: 1,
          failedCount: 1,
          filePath: 'README.md',
          hasTitle: true,
          hasKeywords: true,
          hasSummary: true,
        }),
      );
      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Some chunks failed enrichment',
        expect.objectContaining({
          failedCount: 1,
          totalChunks: 2,
          filePath: 'README.md',
          firstFailureReason: 'second chunk boom',
        }),
      );
    });

    it('does NOT emit Some chunks failed enrichment when all chunks are enriched', async () => {
      enableEnrichment();

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest.fn().mockReturnValue([enrichedChunk('T')]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([
          { text: 'A', metadata: {} },
          { text: 'B', metadata: {} },
        ]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      const result = await service.chunkFile('# Title\n\nA\n\nB', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toHaveLength(2);

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Extracted metadata; enriched=2, failed=0',
        expect.objectContaining({ totalChunks: 2, enrichedCount: 2, failedCount: 0 }),
      );
      expect(mockLogger.warn).not.toHaveBeenCalledWith(
        '[mastra-chunking:enrichment] Some chunks failed enrichment',
        expect.anything(),
      );
    });
  });

  describe('skipEnrichment override (Task 4 — enrichment-free chunking)', () => {
    const skipSourceConfig: WatchSourceConfig = {
      id: 'test-source',
      path: '/test/path',
      memoryBank: 'test-memoryBank',
      exclude: [],
      debounceMs: 3000,
      sourceType: SOURCE_TYPES.VAULT,
    };

    const setupEnabledEnrichmentDoc = () => {
      configService = createMockConfigService({
        enrichmentEnabled: true,
        enrichmentApiKey: 'test-key',
        enrichmentLlmUrl: 'https://lite-llm.lan/v1',
      });
      service = new MastraChunkingService(configService, mockLogger);

      const mockDoc = {
        extractMetadata: jest.fn().mockResolvedValue({
          getDocs: jest
            .fn()
            .mockReturnValue([
              { text: 'content', metadata: { enrichment: { title: 'T', keywords: 'k', summary: 'S' } } },
            ]),
        }),
        chunkMarkdown: jest.fn(),
        getDocs: jest.fn().mockReturnValue([{ text: 'content', metadata: {} }]),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);
      return mockDoc;
    };

    it('skips extractMetadata (and LLM creation) even when enrichment.enabled is true in config', async () => {
      const mockDoc = setupEnabledEnrichmentDoc();

      const result = await service.chunkFile('# Title', 'README.md', 'test-source', skipSourceConfig, {
        skipEnrichment: true,
      });

      expect(result.isOk()).toBe(true);
      // Behavior: no LLM block ran — no extractMetadata call, no LLM client created,
      // and no enrichment metadata stamped on the chunk.
      expect(mockDoc.extractMetadata).not.toHaveBeenCalled();
      expect(LlmClientFactory.createCustomLlm).not.toHaveBeenCalled();
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBeUndefined();
    });

    it('still runs extractMetadata when skipEnrichment is false while enrichment is enabled', async () => {
      const mockDoc = setupEnabledEnrichmentDoc();

      const result = await service.chunkFile('# Title', 'README.md', 'test-source', skipSourceConfig, {
        skipEnrichment: false,
      });

      expect(result.isOk()).toBe(true);
      expect(mockDoc.extractMetadata).toHaveBeenCalled();
      expect(result.getValue()[0].metadata?.mastraDocTitle).toBe('T');
    });
  });
});
