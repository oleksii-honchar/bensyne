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

// Mock fs/promises with real implementations by default; individual tests can
// override specific methods (e.g. readdir) while keeping stat/readFile/etc. real.
jest.mock('fs/promises', () => {
  const actual = jest.requireActual<typeof import('fs/promises')>('fs/promises');
  return {
    ...actual,
    readdir: jest.fn((...args: Parameters<typeof actual.readdir>) => actual.readdir(...args)),
    stat: jest.fn((...args: Parameters<typeof actual.stat>) => actual.stat(...args)),
  };
});
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
  let sut: AgentSessionChunkingStrategy;
  let mockSessionMetadataService: ReturnType<typeof aSessionMetadataService>;
  let mockMastraChunkingService: ReturnType<typeof aMastraChunkingService>;
  let mockLogger: BasePinoLogger;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSessionMetadataService = aSessionMetadataService();
    mockMastraChunkingService = aMastraChunkingService();
    mockLogger = aLogger();
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastraChunkingService as unknown as MastraChunkingService,
      mockLogger,
    );
  });

  describe('implements ChunkingStrategy', () => {
    it('has chunkFile method with correct signature', () => {
      expect(typeof sut.chunkFile).toBe('function');
    });
  });

  describe('chunkFile with frontmatter', () => {
    it('creates frontmatter chunk with importance 0.9, correct tags and sectionHeader', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
        }),
      );

      const fmChunk = result.getValue()[0];
      expect(fmChunk.text).toMatch(/^---\n[\s\S]*\n---$/);
    });

    it('passes body content (not full content) to MastraChunkingService', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
        }),
      );

      expect(mockSessionMetadataService.extract).toHaveBeenCalled();
    });
  });

  describe('chunkFile without frontmatter', () => {
    it('skips frontmatter chunk and returns only body chunks', async () => {
      const bodyChunk = aBodyChunk();
      mockMastraChunkingService = aMastraChunkingService([bodyChunk]);

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await sut.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        emptyMetaService as unknown as SessionMetadataService,
        emptyMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

        sut = new AgentSessionChunkingStrategy(
          mockSessionMetadataService as unknown as SessionMetadataService,
          mastra as unknown as MastraChunkingService,
          mockLogger,
        );

        const filePath = path.join(subDir, 'file.md');
        await sut.chunkFile(
          WITH_FRONTMATTER,
          filePath,
          'test-source',
          aWatchSourceConfig({
            id: 'test-source',
            path: '/test/path',
            memoryBank: 'test-source',
            exclude: ['**/node_modules/**'],
            sourceType: 'agent-sessions',
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

        sut = new AgentSessionChunkingStrategy(
          mockSessionMetadataService as unknown as SessionMetadataService,
          mastra as unknown as MastraChunkingService,
          mockLogger,
        );

        const filePath = path.join(testDir, 'file.md');
        await sut.chunkFile(
          WITH_FRONTMATTER,
          filePath,
          'test-source',
          aWatchSourceConfig({
            id: 'test-source',
            path: '/test/path',
            memoryBank: 'test-source',
            exclude: ['**/node_modules/**'],
            sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        emptyMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        '',
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
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

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
        }),
      );

      expect(mockMastraChunkingService.chunkFile).toHaveBeenCalledTimes(1);
    });

    it('returns multiple body chunks from Mastra', async () => {
      const chunk1 = aBodyChunk({ chunkIndex: 0 });
      const chunk2 = aBodyChunk({ chunkIndex: 1 });
      const multiMastra = aMastraChunkingService([chunk1, chunk2]);

      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        multiMastra as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        aWatchSourceConfig({
          id: 'test-source',
          path: '/test/path',
          memoryBank: 'test-source',
          exclude: ['**/node_modules/**'],
          sourceType: 'agent-sessions',
        }),
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // 1 frontmatter + 2 body chunks
      expect(chunks.length).toBe(3);
    });
  });

  describe('companion edges', () => {
    let testRoot: string;

    const COMPANION_FILES = [
      'session.md',
      'specifications/spec.md',
      'findings/findings.md',
      'decisions/decisions.md',
      'plans/implementation-plan.md',
      'materials/unified-chunk-contract.md',
    ];

    async function createSessionRoot(companions: string[] = COMPANION_FILES): Promise<string> {
      const root = path.join('/tmp', 'companion-edges-' + Date.now() + '-' + Math.random().toString(36).slice(2));
      for (const rel of companions) {
        const fullPath = path.join(root, rel);
        await fsPromises.mkdir(path.dirname(fullPath), { recursive: true });
        await fsPromises.writeFile(fullPath, 'content');
      }
      return root;
    }

    function createStrategyWithMastra(mastraChunks?: ReturnType<typeof aBodyChunk>[]) {
      const mastra = aMastraChunkingService(mastraChunks ?? [aBodyChunk()]);
      return new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mastra as unknown as MastraChunkingService,
        mockLogger,
      );
    }

    const sourceConfig = aWatchSourceConfig({
      id: 'test-source',
      path: '/test/path',
      memoryBank: 'test-source',
      exclude: ['**/node_modules/**'],
      sourceType: 'agent-sessions',
    });

    afterEach(async () => {
      if (testRoot) {
        await fsPromises.rm(testRoot, { recursive: true, force: true });
      }
    });

    it('emits parent_child edge to session.md and sibling edges for findings/findings.md chunk', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      const result = await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThan(0);

      const chunk = chunks[0];
      const edges = chunk.edges;
      expect(edges).toBeDefined();

      // parent_child edge to session.md
      const parentEdge = edges!.find(
        e => e.relation_type === 'parent_child' && e.target_path === path.join(testRoot, 'session.md'),
      );
      expect(parentEdge).toBeDefined();
      expect(parentEdge!.strength).toBe(1);

      // sibling edges to each other present companion (excluding F itself and session.md)
      const siblingTargets = edges!
        .filter(e => e.relation_type === 'sibling')
        .map(e => e.target_path)
        .sort();

      const expectedSiblings = [
        path.join(testRoot, 'specifications', 'spec.md'),
        path.join(testRoot, 'decisions', 'decisions.md'),
        path.join(testRoot, 'plans', 'implementation-plan.md'),
        path.join(testRoot, 'materials', 'unified-chunk-contract.md'),
      ].sort();

      expect(siblingTargets).toEqual(expectedSiblings);
    });

    it('does NOT emit parent_child edge when chunking session.md itself, but emits sibling edges', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'session.md');

      const result = await sut.chunkFile(
        'Session content',
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const chunk = chunks[0];
      const edges = chunk.edges;
      expect(edges).toBeDefined();

      // No parent_child edge to itself
      const parentEdges = edges!.filter(
        e => e.relation_type === 'parent_child' && e.target_path === path.join(testRoot, 'session.md'),
      );
      expect(parentEdges.length).toBe(0);

      // Sibling edges to other present companions (excluding session.md itself)
      const siblingTargets = edges!
        .filter(e => e.relation_type === 'sibling')
        .map(e => e.target_path)
        .sort();

      const expectedSiblings = [
        path.join(testRoot, 'specifications', 'spec.md'),
        path.join(testRoot, 'findings', 'findings.md'),
        path.join(testRoot, 'decisions', 'decisions.md'),
        path.join(testRoot, 'plans', 'implementation-plan.md'),
        path.join(testRoot, 'materials', 'unified-chunk-contract.md'),
      ].sort();

      expect(siblingTargets).toEqual(expectedSiblings);
    });

    it('emits no edges for absent companions', async () => {
      testRoot = await createSessionRoot(['session.md', 'findings/findings.md']);
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      const result = await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      const chunk = chunks[0];
      const edges = chunk.edges;
      expect(edges).toBeDefined();

      // Only parent_child to session.md, no sibling edges (no other companions)
      const parentEdge = edges!.find(
        e => e.relation_type === 'parent_child' && e.target_path === path.join(testRoot, 'session.md'),
      );
      expect(parentEdge).toBeDefined();

      const siblingEdges = edges!.filter(e => e.relation_type === 'sibling');
      expect(siblingEdges.length).toBe(0);
    });

    it('produces chunk with empty edges when session root is unreadable (fs error)', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      // Simulate fs failure on readdir
      (fsPromises.readdir as jest.Mock).mockRejectedValueOnce(new Error('EACCES'));

      const result = await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBeGreaterThan(0);

      // Edges should be empty or undefined (no exception thrown)
      for (const chunk of chunks) {
        if (chunk.edges !== undefined) {
          expect(chunk.edges).toEqual([]);
        }
      }
    });

    it('makes exactly ONE readdir call per process-file run', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      (fsPromises.readdir as jest.Mock).mockClear();

      await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );

      // locateSessionRoot uses stat (not readdir), so only the companion listing calls readdir
      const rootCalls = (fsPromises.readdir as jest.Mock).mock.calls.filter(
        call => call[0] === testRoot,
      );
      expect(rootCalls.length).toBe(1);
    });

    it('makes exactly ONE readdir call per process-file run (two runs = two calls)', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      (fsPromises.readdir as jest.Mock).mockClear();

      await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );
      await sut.chunkFile(
        'More findings',
        filePath,
        'test-source',
        sourceConfig,
      );

      const rootCalls = (fsPromises.readdir as jest.Mock).mock.calls.filter(
        call => call[0] === testRoot,
      );
      expect(rootCalls.length).toBe(2);
    });

    it('edge target_path values are absolute paths starting with the session root', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      const result = await sut.chunkFile(
        'Findings content',
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      for (const chunk of chunks) {
        if (chunk.edges && chunk.edges.length > 0) {
          for (const edge of chunk.edges) {
            expect(edge.target_path.startsWith(testRoot)).toBe(true);
            expect(path.isAbsolute(edge.target_path)).toBe(true);
          }
        }
      }
    });

    it('preserves existing session-frontmatter metadata behavior alongside edges', async () => {
      testRoot = await createSessionRoot();
      const sut = createStrategyWithMastra();
      const filePath = path.join(testRoot, 'findings', 'findings.md');

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        filePath,
        'test-source',
        sourceConfig,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(2); // frontmatter + body

      // Frontmatter chunk still has session metadata
      const fmMeta = chunks[0].metadata;
      expect(fmMeta?.['session.id']).toBe('ses_test123');
      expect(fmMeta?.['session.status']).toBe('in-progress');

      // Body chunk still has session metadata
      const bodyMeta = chunks[1].metadata;
      expect(bodyMeta?.['session.id']).toBe('ses_test123');
    });
  });

  // --- D41: final-list 0-based dense re-index (clarification A) ---

  describe('final-list 0-based re-index (D41)', () => {
    const d41Config = aWatchSourceConfig({
      id: 'test-source',
      path: '/test/path',
      memoryBank: 'test-source',
      exclude: ['**/node_modules/**'],
      sourceType: 'agent-sessions',
    });

    it('with frontmatter: final list is dense 0-based and every chunk carries totalChunks = length', async () => {
      const chunk1 = aBodyChunk({ chunkIndex: 0 });
      const chunk2 = aBodyChunk({ chunkIndex: 1 });
      mockMastraChunkingService = aMastraChunkingService([chunk1, chunk2]);
      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITH_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        d41Config,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      // 1 frontmatter + 2 body chunks
      expect(chunks.length).toBe(3);
      expect(chunks.map(c => c.chunkIndex)).toEqual([0, 1, 2]);
      for (const chunk of chunks) {
        expect(chunk.totalChunks).toBe(3);
      }
    });

    it('without frontmatter: final list is dense 0-based and every chunk carries totalChunks = length', async () => {
      const chunk1 = aBodyChunk({ chunkIndex: 0 });
      const chunk2 = aBodyChunk({ chunkIndex: 1 });
      mockMastraChunkingService = aMastraChunkingService([chunk1, chunk2]);
      sut = new AgentSessionChunkingStrategy(
        mockSessionMetadataService as unknown as SessionMetadataService,
        mockMastraChunkingService as unknown as MastraChunkingService,
        mockLogger,
      );

      const result = await sut.chunkFile(
        WITHOUT_FRONTMATTER,
        '/test/path/file.md',
        'test-source',
        d41Config,
      );

      expect(result.isOk()).toBe(true);
      const chunks = result.getValue();
      expect(chunks.length).toBe(2);
      expect(chunks.map(c => c.chunkIndex)).toEqual([0, 1]);
      for (const chunk of chunks) {
        expect(chunk.totalChunks).toBe(2);
      }
    });
  });
});
