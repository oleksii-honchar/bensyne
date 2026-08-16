import { FILE_ROLES } from '@/domain/content-chunk.entity';
import { aBodyChunk } from '@/domain/content-chunk.entity.test-utils';
import { SessionMetadata } from '@/domain/session-metadata.type';
import { aWatchSourceConfig } from '@/domain/watch-source.entity.test-utils';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { SessionMetadataService } from '@/infrastructure/services/session-metadata.service';
import { aSessionMetadataService } from '@/infrastructure/services/session-metadata.service.test-utils';
import { splitFrontmatter } from '@/utils/strategy-utils';
import * as fsSync from 'fs';
import * as fsPromises from 'fs/promises';
import * as path from 'path';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { aMastraChunkingService } from './mastra-chunking.service.test-utils';

// --- Test fixtures (loaded from shared fixtures) ---

const TEST_SESSION_MD = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/test-session.md'),
  'utf-8',
);
const WITH_FRONTMATTER = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/with-frontmatter.md'),
  'utf-8',
);
const WITHOUT_FRONTMATTER = fsSync.readFileSync(
  path.resolve(__dirname, '../../e2e/fixtures/without-frontmatter.md'),
  'utf-8',
);

const EMPTY_SESSION_META: SessionMetadata = {
  sessionId: '',
  createdAt: '',
  status: '',
  phase: '',
  nextAgent: '',
};

// --- Tests ---

describe('splitFrontmatter', () => {
  it('extracts frontmatter and body when frontmatter exists', () => {
    const { frontmatter, body } = splitFrontmatter(WITH_FRONTMATTER);

    expect(frontmatter).not.toBeNull();
    expect(frontmatter).toContain('sessionId: ses_test123');
    expect(frontmatter).toContain('status: in-progress');
    expect(body).toBe('\n# Test Document\n\nThis is the body content after frontmatter.\n');
  });

  it('returns null frontmatter when no frontmatter exists', () => {
    const { frontmatter, body } = splitFrontmatter(WITHOUT_FRONTMATTER);

    expect(frontmatter).toBeNull();
    expect(body).toBe(WITHOUT_FRONTMATTER);
  });

  it('handles content with only frontmatter and empty body', () => {
    const content = '---\nkey: value\n---\n';
    const { frontmatter, body } = splitFrontmatter(content);

    expect(frontmatter).toBe('key: value');
    expect(body).toBe('');
  });

  it('handles content with only frontmatter and no trailing newline', () => {
    const content = '---\nkey: value\n---';
    const { frontmatter, body } = splitFrontmatter(content);

    expect(frontmatter).toBe('key: value');
    expect(body).toBe('');
  });

  it('preserves body content with multiple lines', () => {
    const content = '---\nkey: value\n---\n\nLine 1\nLine 2\nLine 3';
    const { frontmatter, body } = splitFrontmatter(content);

    expect(frontmatter).toBe('key: value');
    expect(body).toBe('\nLine 1\nLine 2\nLine 3');
  });
});

describe('AgentSessionChunkingStrategy', () => {
  let strategy: AgentSessionChunkingStrategy;
  let mockSessionMetadataService: ReturnType<typeof aSessionMetadataService>;
  let mockMastraChunkingService: ReturnType<typeof aMastraChunkingService>;
  let mockLogger: BasePinoLogger;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSessionMetadataService = aSessionMetadataService();
    mockMastraChunkingService = aMastraChunkingService();
    mockLogger = aLogger();
    strategy = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastraChunkingService as unknown as MastraChunkingService,
      mockLogger,
    );
  });

  describe('implements ChunkingStrategy', () => {
    it('has chunkFile method with correct signature', () => {
      expect(typeof strategy.chunkFile).toBe('function');
    });
  });

  describe('chunkFile with frontmatter', () => {
    it('creates frontmatter chunk with importance 0.9, correct tags and sectionHeader', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(2);

      // Frontmatter chunk
      const fmChunk = chunks[0];
      expect(fmChunk.importance).toBe(0.9);
      expect(fmChunk.tags).toEqual(['frontmatter', 'metadata']);
      expect(fmChunk.sectionHeader).toBe('Frontmatter');
      expect(fmChunk.text).toContain('---');
      expect(fmChunk.text).toContain('sessionId: ses_test123');
      expect(fmChunk.fileRole).toBe(FILE_ROLES.DOCS);
    });

    it('wraps frontmatter chunk text in --- delimiters', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      const fmChunk = result.getValue()[0];
      expect(fmChunk.text).toMatch(/^---\n[\s\S]*\n---$/);
    });

    it('passes body content (not full content) to MastraChunkingService', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledWith(
        '\n# Test Document\n\nThis is the body content after frontmatter.\n',
        '/test/path/file.md',
        'test-source',
      );
    });

    it('enriches all chunks with session metadata', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      const chunks = result.getValue();

      // Frontmatter chunk metadata
      const fmMeta = chunks[0].metadata;
      expect(fmMeta?.['session.id']).toBe('ses_test123');
      expect(fmMeta?.['session.createdAt']).toBe('2026-07-28T09:46:23Z');
      expect(fmMeta?.['session.status']).toBe('in-progress');
      expect(fmMeta?.['session.phase']).toBe('implementation');
      expect(fmMeta?.['session.nextAgent']).toBe('developer');

      // Body chunk metadata
      const bodyMeta = chunks[1].metadata;
      expect(bodyMeta?.['session.id']).toBe('ses_test123');
      expect(bodyMeta?.['session.createdAt']).toBe('2026-07-28T09:46:23Z');
      expect(bodyMeta?.['session.status']).toBe('in-progress');
      expect(bodyMeta?.['session.phase']).toBe('implementation');
      expect(bodyMeta?.['session.nextAgent']).toBe('developer');
    });

    it('calls SessionMetadataService.extract with session root path', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(mockSessionMetadataService.extract).toHaveBeenCalled();
    });
  });

  describe('chunkFile without frontmatter', () => {
    it('skips frontmatter chunk and returns only body chunks', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(1);
      expect(chunks[0].sectionHeader).not.toBe('Frontmatter');
    });

    it('passes full content to Mastra when no frontmatter', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledWith(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
      );
    });
  });

  describe('session metadata enrichment', () => {
    it('enriches with empty metadata when session metadata is empty', async () => {
      const emptyMetaService = aSessionMetadataService(EMPTY_SESSION_META);
      const bodyChunk = aBodyChunk();
      const emptyMastra = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        emptyMetaService as unknown as SessionMetadataService,
        emptyMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      const chunks = result.getValue();
      const fmMeta = chunks[0].metadata;
      expect(fmMeta?.['session.id']).toBe('');
      expect(fmMeta?.['session.createdAt']).toBe('');
      expect(fmMeta?.['session.status']).toBe('');
      expect(fmMeta?.['session.phase']).toBe('');
      expect(fmMeta?.['session.nextAgent']).toBe('');
    });
  });

  describe('locateSessionRoot', () => {
    it('returns the directory containing session.md when found', async () => {
      const testDir = '/tmp/test-session-root-' + Date.now();
      const subDir = path.join(testDir, 'sub', 'deep');

      try {
        await fsPromises.mkdir(subDir, { recursive: true });
        await fsPromises.writeFile(path.join(testDir, 'session.md'), TEST_SESSION_MD);

        const bodyChunk = aBodyChunk();
        const mastra = aMastraChunkingService([bodyChunk]);

        strategy = new AgentSessionChunkingStrategy(
          mockSessionMetadataService as unknown as SessionMetadataService,
          mastra as unknown as MastraChunkingService,
          mockLogger,
        );

        const filePath = path.join(subDir, 'file.md');
        await strategy.chunkFile(
          WITH_FRONTMATTER,
          filePath,
          'test-source',
          aWatchSourceConfig({
            id: 'test-source',
            path: '/test/path',
            memoryBank: 'test-source',
            exclude: ['**/node_modules/**'],
            strategy: 'agent-sessions',
          }),
        );

        expect(mockSessionMetadataService.extract).toHaveBeenCalledWith(testDir);
      } finally {
        await fsPromises.rm(testDir, { recursive: true, force: true });
      }
    });

    it('uses parent directory when session.md not found (graceful)', async () => {
      const testDir = '/tmp/test-no-session-' + Date.now();

      try {
        await fsPromises.mkdir(testDir, { recursive: true });

        const bodyChunk = aBodyChunk();
        const mastra = aMastraChunkingService([bodyChunk]);

        strategy = new AgentSessionChunkingStrategy(
          mockSessionMetadataService as unknown as SessionMetadataService,
          mastra as unknown as MastraChunkingService,
          mockLogger,
        );

        const filePath = path.join(testDir, 'file.md');
        await strategy.chunkFile(
          WITH_FRONTMATTER,
          filePath,
          'test-source',
          aWatchSourceConfig({
            id: 'test-source',
            path: '/test/path',
            memoryBank: 'test-source',
            exclude: ['**/node_modules/**'],
            strategy: 'agent-sessions',
          }),
        );

        // Should call extract with the parent of the file path
        expect(mockSessionMetadataService.extract).toHaveBeenCalledWith(testDir);
      } finally {
        await fsPromises.rm(testDir, { recursive: true, force: true });
      }
    });
  });

  describe('empty content', () => {
    it('returns empty array for empty content', async () => {
      const emptyMastra = aMastraChunkingService([]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        emptyMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        '',
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([]);
    });
  });

  describe('body chunking via Mastra', () => {
    it('delegates body chunking to MastraChunkingService', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledTimes(1);
    });

    it('returns multiple body chunks from Mastra', async () => {
      const chunk1 = aBodyChunk({ chunkIndex: 0 });
      const chunk2 = aBodyChunk({ chunkIndex: 1 });
      const multiMastra = aMastraChunkingService([chunk1, chunk2]);

      strategy = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        multiMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await strategy.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          strategy: 'agent-sessions',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // 1 frontmatter + 2 body chunks
      expect(chunks.length).toBe(3);
    });
  });
});
