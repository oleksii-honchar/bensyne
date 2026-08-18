import '@/utils/mastra-rag.test-utils';

import { LlmClientFactory } from '../../application/services/llm-client-factory';
import { FILE_ROLES } from '../../domain/content-chunk.entity';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';

import { MDocument } from '@mastra/rag';
import { MastraChunkingService } from './mastra-chunking.service';

const mockedMDocument = MDocument as jest.Mocked<typeof MDocument>;

const mockCustomLlm = {} as never;
const mockedLlmClientFactory = LlmClientFactory as jest.Mocked<typeof LlmClientFactory>;

const createMockConfigService = (overrides?: {
  maxCharacters?: Record<string, number>;
  enrichmentEnabled?: boolean;
  enrichmentApiKey?: string | null;
  enrichmentLlmUrl?: string | null;
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
      timeoutMs: 15000,
      docMaxTokens: 16000,
    }),
  } as unknown as ConfigurationService;
};

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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      const callArg = mockDoc.extractMetadata.mock.calls[0][0];
      expect(callArg.schema.llm).toBe(mockCustomLlm);
      expect(callArg.schema.instructions).toBe(
        `You must respond ONLY with valid JSON.

Extract the following fields from the document:
- title: A concise title describing the content
- keywords: Comma-separated keywords

Respond in this format:
{
  "title": "string",
  "keywords": "keyword1, keyword2, keyword3"
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
        expect.stringContaining('[enrichment] ExtractMetadata failed'),
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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      const result = await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(result.isOk()).toBe(true);
      const chunk = result.getValue()[0];
      expect(chunk.metadata?.mastraDocTitle).toBe('Enriched Title');
      expect(chunk.metadata?.mastraDocKeywords).toBe('enriched,keywords');
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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[enrichment] Attempting enrichment',
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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[enrichment] Skipped',
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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[enrichment] Skipped',
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
      };
      mockedMDocument.fromMarkdown.mockReturnValue(mockDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[enrichment] Skipped',
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
        '[enrichment] ExtractMetadata failed',
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
              metadata: { enrichment: { title: 'Enriched Title', keywords: 'enriched,keywords' } },
            },
          ]),
        }),
        chunkMarkdown: jest.fn(),
      };
      mockedMDocument.fromMarkdown.mockReturnValue(enrichedDoc as never);

      await service.chunkFile('# Title', 'README.md', 'test-source');

      expect(mockLogger.info).toHaveBeenCalledWith(
        '[enrichment] Extracted metadata; hasTitle=true, hasKeywords=true',
        expect.objectContaining({
          hasTitle: true,
          hasKeywords: true,
          filePath: 'README.md',
        }),
      );
    });
  });
});
