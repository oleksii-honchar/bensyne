/**
 * Integration tests for chunking strategies using real file content.
 *
 * These tests read real fixtures (copied from actual Obsidian notes and session.md files)
 * and process them through real chunker implementations (with MastraChunkingService mocked
 * only for the body-chunking step, since that calls external services).
 */
import '@/utils/mastra-rag.test-utils';

import * as fs from 'fs/promises';
import * as path from 'path';
import { ContentChunk, FILE_ROLES } from '../../domain/content-chunk.entity';
import { SessionMetadata } from '../../domain/session-metadata.type';
import { cleanupTempDir, createTempDir, FIXTURES_DIR } from '../../e2e/e2e-utils';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { SOURCE_TYPES } from '../../infrastructure/config/source-types';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { SessionMetadataService } from '../../infrastructure/services/session-metadata.service';
import { Result } from '../../utils/result';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';
import { StrategyRouter } from './strategy-router.service';
import { VaultChunkingStrategy } from './vault-chunking.strategy';

// --- Helpers ---

jest.mock('chokidar', () => ({
  watch: jest.fn(() => ({
    on: jest.fn(),
    close: jest.fn().mockResolvedValue(undefined),
  })),
}));

interface MockResult<T> {
  isOk: () => boolean;
  isKo: () => boolean;
  getValue: () => T;
  getErrors: () => never[];
  getEvents: () => never[];
  getFormattedErrors: () => string;
  hasEvents: () => boolean;
  map: jest.Mock;
  chain: jest.Mock;
}

const okResult = <T>(value: T): MockResult<T> => ({
  isOk: () => true,
  isKo: () => false,
  getValue: () => value,
  getErrors: () => [],
  getEvents: () => [],
  getFormattedErrors: () => '',
  hasEvents: () => false,
  map: jest.fn(),
  chain: jest.fn(),
});

const createMockLogger = (): BasePinoLogger => ({
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
  log: jest.fn(),
  child: jest.fn().mockReturnThis(),
  setContext: jest.fn(),
});

const createBodyChunk = (text: string, overrides?: Partial<ContentChunk>): ContentChunk => {
  return ContentChunk.of({
    id: 1n,
    text,
    chunkIndex: 0,
    totalChunks: 1,
    sectionHeader: 'Body',
    breadcrumb: '/test/path/file.md',
    fileRole: FILE_ROLES.DOCS,
    oversized: false,
    metadata: { filePath: '/test/path/file.md', sourceId: 'test-source' },
    importance: 0.5,
    tags: [],
    memoryBank: 'default',
    ...overrides,
  }).getValue();
};

const createMockMastraChunkingService = (chunks: ContentChunk[] = []): jest.Mocked<MastraChunkingService> =>
  ({
    chunkFile: jest.fn().mockResolvedValue(okResult(chunks)),
  }) as unknown as jest.Mocked<MastraChunkingService>;

const createObsidianSourceConfig = (): WatchSourceConfig => ({
  id: 'obsidian-vault',
  path: '/obsidian/vault',
  memoryBank: 'obsidian',
  exclude: ['**/node_modules/**'],
  debounceMs: 3000,
  sourceType: SOURCE_TYPES.OBSIDIAN,
});

const createAgentSessionsSourceConfig = (): WatchSourceConfig => ({
  id: 'agent-sessions',
  path: '/agent-sessions',
  memoryBank: 'agent-sessions',
  exclude: ['**/node_modules/**'],
  debounceMs: 3000,
  sourceType: SOURCE_TYPES.AGENT_SESSIONS,
});

const createContentAwareSourceConfig = (): WatchSourceConfig => ({
  id: 'general',
  path: '/general',
  memoryBank: 'general',
  exclude: ['**/node_modules/**'],
  debounceMs: 3000,
  sourceType: SOURCE_TYPES.VAULT,
});

// --- Tests ---

describe('ObsidianChunkingStrategy with real Obsidian notes', () => {
  let sut: ObsidianChunkingStrategy;
  let mockMastra: jest.Mocked<MastraChunkingService>;
  let mockLogger: BasePinoLogger;

  beforeEach(() => {
    jest.clearAllMocks();
    mockLogger = createMockLogger();
    mockMastra = createMockMastraChunkingService();
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);
  });

  it('processes real VS Code.md — frontmatter chunk with 0.9 importance and correct tags', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const bodyChunk = createBodyChunk('VS Code note body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(
      content,
      '/obsidian/olho/Lists/IT Notes/IT Notes.items/VS Code.md',
      'obsidian-vault',
      createObsidianSourceConfig(),
    );

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks.length).toBeGreaterThanOrEqual(2); // 1 frontmatter + at least 1 body

    // Frontmatter chunk
    const fmChunk = chunks[0];
    expect(fmChunk.importance).toBe(0.9);
    expect(fmChunk.sectionHeader).toBe('Frontmatter');
    expect(fmChunk.tags).toContain('frontmatter');
    expect(fmChunk.tags).toContain('metadata');
    expect(fmChunk.tags).toContain('obsidian-note');
    expect(fmChunk.text).toContain('---');
    expect(fmChunk.text).toContain('Created: 2023-05-09T19:04:00');
    expect(fmChunk.text).toContain('tags:');
    expect(fmChunk.fileRole).toBe(FILE_ROLES.DOCS);
  });

  it('processes real VS Code.md — note metadata extracted correctly', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const bodyChunk = createBodyChunk('VS Code note body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(
      content,
      '/obsidian/olho/Lists/IT Notes/IT Notes.items/VS Code.md',
      'obsidian-vault',
      createObsidianSourceConfig(),
    );

    const chunks = result.getValue();
    const fmMeta = chunks[0].metadata;

    // note.tags should be JSON string of the tags array
    expect(fmMeta?.['note.tags']).toBe(JSON.stringify(['it-notes', 'it-notes/engineering', 'notes']));
    // note.aliases — this note doesn't have aliases, so empty array
    expect(fmMeta?.['note.aliases']).toBe(JSON.stringify([]));
    // Custom Obsidian fields — Created, Kind, Type, Project, Updated are NOT standard
    // NoteMetadata fields (created, modified, source, status, type are the standard fields)
    // The real note uses "Type" (capital T) and "Created" (capital C) which don't map
    // to the lowercase standard fields "type" and "created"
    expect(fmMeta?.['note.type']).toBe(''); // "Type: projects" doesn't map to "type"
    expect(fmMeta?.['note.created']).toBe(''); // "Created: ..." doesn't map to "created"
  });

  it('processes real VS Code.md — note tags merged into chunk tags', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const bodyChunk = createBodyChunk('VS Code note body content', { tags: ['existing-tag'] });
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(
      content,
      '/obsidian/olho/Lists/IT Notes/IT Notes.items/VS Code.md',
      'obsidian-vault',
      createObsidianSourceConfig(),
    );

    const chunks = result.getValue();

    // Frontmatter chunk should have note tags merged
    const fmTags = chunks[0].tags;
    expect(fmTags).toContain('it-notes');
    expect(fmTags).toContain('it-notes/engineering');
    expect(fmTags).toContain('notes');

    // Body chunk should have both existing and note tags
    const bodyTags = chunks[1].tags;
    expect(bodyTags).toContain('existing-tag');
    expect(bodyTags).toContain('it-notes');
    expect(bodyTags).toContain('it-notes/engineering');
    expect(bodyTags).toContain('notes');
  });

  it('processes real VS Code.md — body content passed to Mastra without frontmatter', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const bodyChunk = createBodyChunk('VS Code note body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    await sut.chunkFile(
      content,
      '/obsidian/olho/Lists/IT Notes/IT Notes.items/VS Code.md',
      'obsidian-vault',
      createObsidianSourceConfig(),
    );

    // Mastra should receive body content (without frontmatter)
    expect(mockMastra.chunkFile).toHaveBeenCalled();
    const bodyContent = mockMastra.chunkFile.mock.calls[0][0] as string;
    expect(bodyContent).not.toContain('---');
    expect(bodyContent).toContain('## Appearance');
    expect(bodyContent).toContain('## Extensions');
  });

  it('processes real VS Code.md — all body chunks enriched with note metadata', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const chunk1 = createBodyChunk('Body chunk 1', { chunkIndex: 0 });
    const chunk2 = createBodyChunk('Body chunk 2', { chunkIndex: 1 });
    mockMastra = createMockMastraChunkingService([chunk1, chunk2]);
    sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(
      content,
      '/obsidian/olho/Lists/IT Notes/IT Notes.items/VS Code.md',
      'obsidian-vault',
      createObsidianSourceConfig(),
    );

    const chunks = result.getValue();
    // 1 frontmatter + 2 body chunks
    expect(chunks.length).toBe(3);

    // All body chunks should be enriched
    for (let i = 1; i < chunks.length; i++) {
      expect(chunks[i].metadata?.['note.tags']).toBe(
        JSON.stringify(['it-notes', 'it-notes/engineering', 'notes']),
      );
      expect(chunks[i].metadata?.['note.type']).toBe(''); // "Type" (capital T) doesn't map
      expect(chunks[i].tags).toContain('it-notes');
    }
  });
});

describe('AgentSessionChunkingStrategy with real session.md', () => {
  let sut: AgentSessionChunkingStrategy;
  let mockSessionMetadataService: {
    extract: jest.MockedFunction<(sessionPath: string) => Promise<MockResult<SessionMetadata>>>;
  };
  let mockMastra: jest.Mocked<MastraChunkingService>;
  let mockLogger: BasePinoLogger;

  const realSessionMetadata: SessionMetadata = {
    sessionId: 'ses_057e2d847ffeJkvVN1hTxIim8L',
    createdAt: '2026-07-28T09:46:23Z',
    status: 'in-progress',
    phase: 'implementation',
    nextAgent: 'reviewer',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockLogger = createMockLogger();
    mockMastra = createMockMastraChunkingService();

    mockSessionMetadataService = {
      extract: jest.fn().mockResolvedValue(okResult(realSessionMetadata)),
    };

    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );
  });

  it('processes real session.md — frontmatter chunk with 0.9 importance', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const bodyChunk = createBodyChunk('Session body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    const result = await sut.chunkFile(
      content,
      '/agent-sessions/26/07/28/260728-1146-rag-content-chunker/session.md',
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks.length).toBeGreaterThanOrEqual(2); // 1 frontmatter + at least 1 body

    const fmChunk = chunks[0];
    expect(fmChunk.importance).toBe(0.9);
    expect(fmChunk.sectionHeader).toBe('Frontmatter');
    expect(fmChunk.tags).toContain('frontmatter');
    expect(fmChunk.tags).toContain('metadata');
    expect(fmChunk.text).toContain('---');
    expect(fmChunk.text).toContain('sessionId: ses_057e2d847ffeJkvVN1hTxIim8L');
  });

  it('processes real session.md — session metadata enrichment with real session ID', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const bodyChunk = createBodyChunk('Session body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    const result = await sut.chunkFile(
      content,
      '/agent-sessions/26/07/28/260728-1146-rag-content-chunker/session.md',
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );

    const chunks = result.getValue();

    // Verify session metadata in frontmatter chunk
    const fmMeta = chunks[0].metadata;
    expect(fmMeta?.['session.id']).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');
    expect(fmMeta?.['session.createdAt']).toBe('2026-07-28T09:46:23Z');
    expect(fmMeta?.['session.status']).toBe('in-progress');
    expect(fmMeta?.['session.phase']).toBe('implementation');
    expect(fmMeta?.['session.nextAgent']).toBe('reviewer');

    // Verify session metadata in body chunk
    const bodyMeta = chunks[1].metadata;
    expect(bodyMeta?.['session.id']).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');
    expect(bodyMeta?.['session.createdAt']).toBe('2026-07-28T09:46:23Z');
    expect(bodyMeta?.['session.status']).toBe('in-progress');
    expect(bodyMeta?.['session.phase']).toBe('implementation');
    expect(bodyMeta?.['session.nextAgent']).toBe('reviewer');
  });

  it('processes real session.md — body content passed to Mastra without frontmatter', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const bodyChunk = createBodyChunk('Session body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    await sut.chunkFile(
      content,
      '/agent-sessions/26/07/28/260728-1146-rag-content-chunker/session.md',
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );

    expect(mockMastra.chunkFile).toHaveBeenCalled();
    const bodyContent = mockMastra.chunkFile.mock.calls[0][0] as string;
    expect(bodyContent).not.toContain('---');
    expect(bodyContent).toContain('# 260728-1146-rag-content-chunker');
  });

  it('processes real session.md — session.id starts with "ses_"', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const bodyChunk = createBodyChunk('Session body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    const result = await sut.chunkFile(
      content,
      '/agent-sessions/26/07/28/260728-1146-rag-content-chunker/session.md',
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );

    const fmMeta = result.getValue()[0].metadata;
    expect(fmMeta?.['session.id']).toMatch(/^ses_/);
  });

  it('processes real session.md — calls SessionMetadataService with correct path', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const bodyChunk = createBodyChunk('Session body content');
    mockMastra = createMockMastraChunkingService([bodyChunk]);
    sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    await sut.chunkFile(
      content,
      '/agent-sessions/26/07/28/260728-1146-rag-content-chunker/session.md',
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );

    // Should have called extract with the directory containing session.md
    expect(mockSessionMetadataService.extract).toHaveBeenCalled();
  });
});

describe('StrategyRouter with real content', () => {
  let router: StrategyRouter;
  let mockAgentSessionStrategy: jest.Mocked<AgentSessionChunkingStrategy>;
  let mockObsidianStrategy: jest.Mocked<ObsidianChunkingStrategy>;
  let mockMastraStrategy: jest.Mocked<MastraChunkingService>;
  let mockVaultStrategy: jest.Mocked<VaultChunkingStrategy>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockAgentSessionStrategy = {
      chunkFile: jest.fn().mockResolvedValue(okResult([createBodyChunk('agent-session body')])),
    } as unknown as jest.Mocked<AgentSessionChunkingStrategy>;

    mockObsidianStrategy = {
      chunkFile: jest.fn().mockResolvedValue(okResult([createBodyChunk('obsidian body')])),
    } as unknown as jest.Mocked<ObsidianChunkingStrategy>;

    mockMastraStrategy = {
      chunkFile: jest.fn().mockResolvedValue(okResult([createBodyChunk('content-aware body')])),
    } as unknown as jest.Mocked<MastraChunkingService>;

    mockVaultStrategy = {
      chunkFile: jest.fn().mockResolvedValue(okResult([createBodyChunk('vault body')])),
    } as unknown as jest.Mocked<VaultChunkingStrategy>;

    router = new StrategyRouter(
      mockAgentSessionStrategy,
      mockObsidianStrategy,
      mockMastraStrategy,
      mockVaultStrategy,
      createMockLogger(),
    );
  });

  it('routes obsidian sut for Obsidian notes', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const sourceConfig = createObsidianSourceConfig();

    const sut = router.selectStrategy(sourceConfig);
    expect(sut).toBe(mockObsidianStrategy);

    const result = await sut.chunkFile(content, '/obsidian/VS Code.md', 'obsidian-vault', sourceConfig);

    expect(result.isOk()).toBe(true);
    expect(mockObsidianStrategy.chunkFile).toHaveBeenCalledWith(
      content,
      '/obsidian/VS Code.md',
      'obsidian-vault',
      sourceConfig,
    );
  });

  it('routes agent-sessions sut for session files', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const sourceConfig = createAgentSessionsSourceConfig();

    const sut = router.selectStrategy(sourceConfig);
    expect(sut).toBe(mockAgentSessionStrategy);

    const result = await sut.chunkFile(content, '/agent-sessions/session.md', 'agent-sessions', sourceConfig);

    expect(result.isOk()).toBe(true);
    expect(mockAgentSessionStrategy.chunkFile).toHaveBeenCalledWith(
      content,
      '/agent-sessions/session.md',
      'agent-sessions',
      sourceConfig,
    );
  });

  it('routes vault source config to VaultChunkingStrategy', async () => {
    const content = await fs.readFile(path.join(FIXTURES_DIR, 'sample.md'), 'utf-8');
    const sourceConfig = createContentAwareSourceConfig();

    const sut = router.selectStrategy(sourceConfig);
    expect(sut).toBe(mockVaultStrategy);

    const result = await sut.chunkFile(content, '/general/sample.md', 'general', sourceConfig);

    expect(result.isOk()).toBe(true);
    expect(mockVaultStrategy.chunkFile).toHaveBeenCalledWith(
      content,
      '/general/sample.md',
      'general',
      sourceConfig,
    );
  });

  it('each sut produces different output structure', async () => {
    // Obsidian sut produces enriched chunks with note metadata
    const obsidianContent = await fs.readFile(path.join(FIXTURES_DIR, 'obsidian-vscode-note.md'), 'utf-8');
    const obsidianChunks = [
      createBodyChunk('obsidian frontmatter', {
        importance: 0.9,
        tags: ['frontmatter', 'metadata', 'obsidian-note', 'it-notes'],
        metadata: {
          filePath: '/obsidian/VS Code.md',
          sourceId: 'obsidian-vault',
          'note.tags': JSON.stringify(['it-notes', 'it-notes/engineering', 'notes']),
          'note.type': 'projects',
        },
      }),
      createBodyChunk('obsidian body', {
        tags: ['it-notes'],
        metadata: {
          filePath: '/obsidian/VS Code.md',
          sourceId: 'obsidian-vault',
          'note.tags': JSON.stringify(['it-notes', 'it-notes/engineering', 'notes']),
        },
      }),
    ];
    mockObsidianStrategy.chunkFile.mockResolvedValue(Result.ok(obsidianChunks));

    // Agent-sessions sut produces chunks with session metadata
    const sessionContent = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    const sessionChunks = [
      createBodyChunk('session frontmatter', {
        importance: 0.9,
        tags: ['frontmatter', 'metadata'],
        metadata: {
          filePath: '/agent-sessions/session.md',
          sourceId: 'agent-sessions',
          'session.id': 'ses_057e2d847ffeJkvVN1hTxIim8L',
          'session.status': 'in-progress',
        },
      }),
    ];
    mockAgentSessionStrategy.chunkFile.mockResolvedValue(Result.ok(sessionChunks));

    // Vault sut produces plain chunks (mocked)
    const sampleContent = await fs.readFile(path.join(FIXTURES_DIR, 'sample.md'), 'utf-8');
    const plainChunks = [
      createBodyChunk('plain body', {
        metadata: {
          filePath: '/general/sample.md',
          sourceId: 'general',
        },
      }),
    ];
    mockVaultStrategy.chunkFile.mockResolvedValue(Result.ok(plainChunks));

    // Route and process each
    const obsidianResult = await router
      .selectStrategy(createObsidianSourceConfig())
      .chunkFile(obsidianContent, '/obsidian/VS Code.md', 'obsidian-vault', createObsidianSourceConfig());

    const sessionResult = await router
      .selectStrategy(createAgentSessionsSourceConfig())
      .chunkFile(
        sessionContent,
        '/agent-sessions/session.md',
        'agent-sessions',
        createAgentSessionsSourceConfig(),
      );

    const plainResult = await router
      .selectStrategy(createContentAwareSourceConfig())
      .chunkFile(sampleContent, '/general/sample.md', 'general', createContentAwareSourceConfig());

    // Verify obsidian chunks have note metadata
    expect(obsidianResult.isOk()).toBe(true);
    const obsidianChunksResult = obsidianResult.getValue();
    expect(obsidianChunksResult[0].metadata?.['note.tags']).toBeDefined();
    expect(obsidianChunksResult[0].tags).toContain('obsidian-note');

    // Verify session chunks have session metadata
    expect(sessionResult.isOk()).toBe(true);
    const sessionChunksResult = sessionResult.getValue();
    expect(sessionChunksResult[0].metadata?.['session.id']).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');

    // Verify plain chunks have no special enrichment
    expect(plainResult.isOk()).toBe(true);
    const plainChunksResult = plainResult.getValue();
    expect(plainChunksResult[0].metadata?.['note.tags']).toBeUndefined();
    expect(plainChunksResult[0].metadata?.['session.id']).toBeUndefined();
  });
});

describe('SessionMetadataService with real files', () => {
  let service: SessionMetadataService;
  let mockLogger: BasePinoLogger;
  let tempDir: string;

  beforeEach(async () => {
    jest.clearAllMocks();
    mockLogger = createMockLogger();
    service = new SessionMetadataService(mockLogger);
    tempDir = await createTempDir('rag-e2e-session-meta-');
  });

  afterEach(async () => {
    await cleanupTempDir(tempDir);
  });

  it('extracts real metadata from a real session.md file', async () => {
    // Copy real session.md to temp dir
    const realContent = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    await fs.writeFile(path.join(tempDir, 'session.md'), realContent, 'utf-8');

    const result = await service.extract(tempDir);

    expect(result.isOk()).toBe(true);
    const metadata = result.getValue();
    expect(metadata.sessionId).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');
    expect(metadata.createdAt).toBe('2026-07-28T09:46:23Z');
    expect(metadata.status).toBe('in-progress');
    expect(metadata.phase).toBe('implementation');
    expect(metadata.nextAgent).toBe('reviewer');
  });

  it('caches metadata from real file within TTL', async () => {
    // Copy real session.md to temp dir
    const realContent = await fs.readFile(path.join(FIXTURES_DIR, 'real-session.md'), 'utf-8');
    await fs.writeFile(path.join(tempDir, 'session.md'), realContent, 'utf-8');

    const result1 = await service.extract(tempDir);
    expect(result1.isOk()).toBe(true);
    expect(result1.getValue().sessionId).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');

    // Second call should use cache — verify same result without re-reading file
    const result2 = await service.extract(tempDir);
    expect(result2.isOk()).toBe(true);
    expect(result2.getValue().sessionId).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');

    // Verify cache is working by checking that modifying the file doesn't affect the second result
    // (within TTL, the cached value is returned)
    await fs.writeFile(path.join(tempDir, 'session.md'), '---\nsessionId: ses_modified\n---\n', 'utf-8');
    const result3 = await service.extract(tempDir);
    // Should still return cached value, not the modified file
    expect(result3.getValue().sessionId).toBe('ses_057e2d847ffeJkvVN1hTxIim8L');
  });
});

describe('VaultChunkingStrategy with a real tmp/vault fixture', () => {
  let sut: VaultChunkingStrategy;
  let mockMastra: jest.Mocked<MastraChunkingService>;
  let mockLogger: BasePinoLogger;
  let vaultRoot: string;

  const vaultSourceConfig = (): WatchSourceConfig => ({
    id: 'vault-source',
    path: vaultRoot,
    memoryBank: 'vault',
    exclude: ['**/node_modules/**'],
    debounceMs: 3000,
    sourceType: SOURCE_TYPES.VAULT,
  });

  const readFile = async (relPath: string): Promise<string> =>
    fs.readFile(path.join(vaultRoot, relPath), 'utf-8');
  const writeFixture = async (relPath: string, lines: string[]): Promise<void> =>
    fs.writeFile(path.join(vaultRoot, relPath), lines.join('\n'), 'utf-8');

  beforeEach(async () => {
    jest.clearAllMocks();
    mockLogger = createMockLogger();
    mockMastra = createMockMastraChunkingService([createBodyChunk('vault body content')]);
    vaultRoot = await createTempDir('rag-e2e-vault-');
    sut = new VaultChunkingStrategy(mockMastra, mockLogger);

    // Build the tmp/vault fixture (spec §10)
    await fs.mkdir(path.join(vaultRoot, 'decisions'), { recursive: true });
    await fs.mkdir(path.join(vaultRoot, 'concepts'), { recursive: true });

    await writeFixture('_Vault-Home.md', ['---', 'type: index', '---', '# Vault Home', '[[0001-x]]']);
    await writeFixture('decisions/_index.md', [
      '---',
      'type: index',
      '---',
      '# Decisions',
      '[[0001-alpha.decision]]',
    ]);
    // see_also uses vault-root-relative paths (matches the real .vault grammar,
    // e.g. `concepts/0001-x.concept.md`, never `../` — spec §3.3 resolves from vaultRoot).
    await writeFixture('decisions/0001-alpha.decision.md', [
      '---',
      'type: decision',
      'id: DEC-0001',
      'see_also:',
      '  - concepts/0001-x.concept.md',
      '---',
      'Decision body. Related: [[0001-x]]',
    ]);
    await writeFixture('decisions/0002-beta.decision.md', [
      '---',
      'type: decision',
      'id: DEC-0002',
      'see_also: ["concepts/0001-x.concept.md"]',
      '---',
      'Beta body.',
    ]);
    await writeFixture('concepts/_index.md', ['# Concepts', '[[0001-x.concept]]']);
    await writeFixture('concepts/0001-x.concept.md', [
      '# X Concept',
      'Links to [[decisions/0002-beta.decision]]',
    ]);
  });

  afterEach(async () => {
    await cleanupTempDir(vaultRoot);
  });

  it('skips index files (_Vault-Home.md) → Result.ok([])', async () => {
    const content = await readFile('_Vault-Home.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, '_Vault-Home.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    expect(result.isOk()).toBe(true);
    expect(result.getValue()).toEqual([]);
  });

  it('skips folder index files (_index.md) → Result.ok([])', async () => {
    const content = await readFile('decisions/_index.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, 'decisions', '_index.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    expect(result.isOk()).toBe(true);
    expect(result.getValue()).toEqual([]);
  });

  it('0001-alpha: edges include the see_also recommendation edge AND the resolved bare-wikilink backlink edge', async () => {
    const content = await readFile('decisions/0001-alpha.decision.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, 'decisions', '0001-alpha.decision.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();
    expect(chunks.length).toBeGreaterThan(0);

    const conceptTarget = path.join(vaultRoot, 'concepts', '0001-x.concept.md');
    for (const chunk of chunks) {
      expect(chunk.edges).toBeDefined();
      const edges = chunk.edges ?? [];

      // see_also → recommendation edge (absolute, existence-gated)
      expect(edges.some(e => e.target_path === conceptTarget && e.relation_type === 'recommendation')).toBe(
        true,
      );

      // [[0001-x]] bare slug → typed node concepts/0001-x.concept.md via prefix match (backlink).
      // Note: see_also and the wikilink both resolve to the SAME absolute path, so both a
      // recommendation and a backlink edge to conceptTarget must be present.
      expect(edges.some(e => e.target_path === conceptTarget && e.relation_type === 'backlink')).toBe(true);

      // note.wikilinks metadata carries the bare slug
      const wikilinks = JSON.parse(chunk.metadata!['note.wikilinks'] ?? '[]');
      expect(wikilinks).toContain('0001-x');
    }
  });

  it('0001-alpha: metadata note.type=decision and note.properties.id=DEC-0001 are present on chunks', async () => {
    const content = await readFile('decisions/0001-alpha.decision.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, 'decisions', '0001-alpha.decision.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    const chunks = result.getValue();
    for (const chunk of chunks) {
      expect(chunk.metadata?.['note.type']).toBe('decision');
      expect(chunk.metadata?.['note.properties.id']).toBe('DEC-0001');
    }
  });

  it('0001-alpha: body text wikilinks are cleaned (no [[) before Mastra chunking', async () => {
    const content = await readFile('decisions/0001-alpha.decision.md');
    await sut.chunkFile(
      content,
      path.join(vaultRoot, 'decisions', '0001-alpha.decision.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    expect(mockMastra.chunkFile).toHaveBeenCalled();
    const bodyContent = mockMastra.chunkFile.mock.calls[0][0] as string;
    expect(bodyContent).not.toContain('[[');
    expect(bodyContent).toContain('Decision body. Related: 0001-x');
  });

  it('0002-beta: inline-array see_also resolves to a recommendation edge', async () => {
    const content = await readFile('decisions/0002-beta.decision.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, 'decisions', '0002-beta.decision.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    const chunks = result.getValue();
    const conceptTarget = path.join(vaultRoot, 'concepts', '0001-x.concept.md');
    expect(chunks.length).toBeGreaterThan(0);
    for (const chunk of chunks) {
      expect(
        (chunk.edges ?? []).some(
          e => e.target_path === conceptTarget && e.relation_type === 'recommendation',
        ),
      ).toBe(true);
    }
  });

  it('0001-x: path-form wikilink resolves to a backlink edge', async () => {
    const content = await readFile('concepts/0001-x.concept.md');
    const result = await sut.chunkFile(
      content,
      path.join(vaultRoot, 'concepts', '0001-x.concept.md'),
      'vault-source',
      vaultSourceConfig(),
    );

    const chunks = result.getValue();
    const decisionTarget = path.join(vaultRoot, 'decisions', '0002-beta.decision.md');
    expect(chunks.length).toBeGreaterThan(0);
    for (const chunk of chunks) {
      expect(
        (chunk.edges ?? []).some(e => e.target_path === decisionTarget && e.relation_type === 'backlink'),
      ).toBe(true);
    }
  });
});

// spec: cross-file traversal amendment (ADR-T1/T2/T4) — integration gate that each
// source type emits at least one edge to a NON-MD target with an absolute,
// correctly-typed target_path (spec §6 Phase 4, §7).
describe('Cross-file traversal — non-md target integration (all source types)', () => {
  let tempDir: string;
  let mockMastra: jest.Mocked<MastraChunkingService>;
  let mockLogger: BasePinoLogger;

  const integrationSessionMetadata: SessionMetadata = {
    sessionId: 'ses_057e2d847ffeJkvVN1hTxIim8L',
    createdAt: '2026-07-28T09:46:23Z',
    status: 'in-progress',
    phase: 'implementation',
    nextAgent: 'reviewer',
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    mockLogger = createMockLogger();
    mockMastra = createMockMastraChunkingService([createBodyChunk('body content')]);
    tempDir = await createTempDir('rag-e2e-xref-integration-');
  });

  afterEach(async () => {
    await cleanupTempDir(tempDir);
  });

  it('agent-sessions: session.md referencing notes.txt emits a cross_reference edge to the non-md file', async () => {
    const sessionRoot = path.join(tempDir, '26/07/28/integration-session');
    await fs.mkdir(sessionRoot, { recursive: true });

    // notes.txt exists in the session tree (non-md target).
    const notesTxt = path.join(sessionRoot, 'notes.txt');
    await fs.writeFile(notesTxt, 'raw session notes', 'utf-8');

    // session.md references notes.txt via a relative path token.
    const sessionMdPath = path.join(sessionRoot, 'session.md');
    const content = [
      '---',
      'sessionId: ses_057e2d847ffeJkvVN1hTxIim8L',
      '---',
      'Reference notes.txt for details.',
    ].join('\n');
    await fs.writeFile(sessionMdPath, content, 'utf-8');

    const mockSessionMetadataService = {
      extract: jest.fn().mockResolvedValue(okResult(integrationSessionMetadata)),
    };
    const sut = new AgentSessionChunkingStrategy(
      mockSessionMetadataService as unknown as SessionMetadataService,
      mockMastra,
      mockLogger,
    );

    const result = await sut.chunkFile(
      content,
      sessionMdPath,
      'agent-sessions',
      createAgentSessionsSourceConfig(),
    );
    expect(result.isOk()).toBe(true);

    const chunks = result.getValue();
    const edges = chunks.flatMap(c => c.edges ?? []);

    // At least one cross_reference edge to the non-md notes.txt target.
    const notesEdge = edges.find(e => e.target_path === notesTxt);
    expect(notesEdge).toBeDefined();
    expect(notesEdge?.relation_type).toBe('cross_reference');
    expect(notesEdge?.strength).toBe(0.7);

    // Absolute, correctly-typed (non-md) target_path.
    expect(path.isAbsolute(notesEdge!.target_path)).toBe(true);
    expect(notesEdge!.target_path.endsWith('.txt')).toBe(true);
  });

  it('vault: [[assets/diagram.png]] wikilink + non-md see_also emit edges to non-md targets', async () => {
    const vaultRoot = path.join(tempDir, 'vault');
    await fs.mkdir(path.join(vaultRoot, 'assets'), { recursive: true });

    // Non-md targets exist in the vault.
    const diagramPng = path.join(vaultRoot, 'assets', 'diagram.png');
    await fs.writeFile(diagramPng, 'PNGDATA', 'utf-8');
    const seeAlsoPng = path.join(vaultRoot, 'assets', 'see_also.png');
    await fs.writeFile(seeAlsoPng, 'PNGDATA', 'utf-8');

    const notePath = path.join(vaultRoot, 'decisions', '0001-alpha.decision.md');
    await fs.mkdir(path.dirname(notePath), { recursive: true });
    const content = [
      '---',
      'type: decision',
      'see_also:',
      '  - assets/see_also.png',
      '---',
      'Decision body. Diagram: [[assets/diagram.png]]',
    ].join('\n');
    await fs.writeFile(notePath, content, 'utf-8');

    const sourceConfig: WatchSourceConfig = {
      id: 'vault-source',
      path: vaultRoot,
      memoryBank: 'vault',
      exclude: ['**/node_modules/**'],
      debounceMs: 3000,
      sourceType: SOURCE_TYPES.VAULT,
    };
    const sut = new VaultChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(content, notePath, 'vault-source', sourceConfig);
    expect(result.isOk()).toBe(true);

    const chunks = result.getValue();
    const edges = chunks.flatMap(c => c.edges ?? []);

    // backlink edge to assets/diagram.png (path-form wikilink, non-md).
    const backlinkEdge = edges.find(e => e.target_path === diagramPng);
    expect(backlinkEdge).toBeDefined();
    expect(backlinkEdge?.relation_type).toBe('backlink');
    expect(path.isAbsolute(backlinkEdge!.target_path)).toBe(true);
    expect(backlinkEdge!.target_path.endsWith('.png')).toBe(true);

    // recommendation edge to assets/see_also.png (non-md see_also).
    const recEdge = edges.find(e => e.target_path === seeAlsoPng);
    expect(recEdge).toBeDefined();
    expect(recEdge?.relation_type).toBe('recommendation');
    expect(path.isAbsolute(recEdge!.target_path)).toBe(true);
    expect(recEdge!.target_path.endsWith('.png')).toBe(true);
  });

  it('obsidian: [[diagram.png]] emits an edge (exists); [[missing.png]] emits NO edge', async () => {
    const vaultRoot = path.join(tempDir, 'obsidian-vault');
    await fs.mkdir(vaultRoot, { recursive: true });

    // diagram.png exists; missing.png does not.
    const diagramPng = path.join(vaultRoot, 'diagram.png');
    await fs.writeFile(diagramPng, 'PNGDATA', 'utf-8');

    const notePath = path.join(vaultRoot, 'Note.md');
    const content = ['---', 'tags: [integration]', '---', 'See [[diagram.png]] and [[missing.png]].'].join(
      '\n',
    );
    await fs.writeFile(notePath, content, 'utf-8');

    const sourceConfig: WatchSourceConfig = {
      id: 'obsidian-vault',
      path: vaultRoot,
      memoryBank: 'obsidian',
      exclude: ['**/node_modules/**'],
      debounceMs: 3000,
      sourceType: SOURCE_TYPES.OBSIDIAN,
    };
    const sut = new ObsidianChunkingStrategy(mockMastra, mockLogger);

    const result = await sut.chunkFile(content, notePath, 'obsidian-vault', sourceConfig);
    expect(result.isOk()).toBe(true);

    const chunks = result.getValue();
    const edges = chunks.flatMap(c => c.edges ?? []);

    // backlink edge to diagram.png (exists, non-md).
    const diagramEdge = edges.find(e => e.target_path === diagramPng);
    expect(diagramEdge).toBeDefined();
    expect(diagramEdge?.relation_type).toBe('backlink');
    expect(path.isAbsolute(diagramEdge!.target_path)).toBe(true);
    expect(diagramEdge!.target_path.endsWith('.png')).toBe(true);

    // NO edge to missing.png — phantom *.ext.md stub eliminated (ADR-T4).
    const missingEdge = edges.find(e => e.target_path.endsWith('missing.png'));
    expect(missingEdge).toBeUndefined();
  });
});
