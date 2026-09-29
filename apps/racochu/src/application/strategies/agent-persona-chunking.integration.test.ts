/**
 * Integration test: agent-persona chunking through the REAL strategy + REAL
 * ChunkContentUseCase, against the REAL threads-operator persona tree fixture.
 *
 * Regression target: the "remember request too large" 405 bug. The persona
 * entry file (00-entry.md) is small (~971 chars) but its chunk carries a rich
 * envelope (13 decision/hierarchy edges + sourceType/fileHash/chunkHash
 * metadata), which serializes to ~4.8KB — above the OLD hardcoded 4000-byte
 * clamp. The old clamp duplicated the full envelope onto EVERY fragment,
 * shrinking the text budget to ~2 chars per fragment and exploding the single
 * node into hundreds of near-empty chunks (405 "request too large" on the wire,
 * since the client guard is 8000 bytes).
 *
 * With the fix (configured serverRequestBodyLimit 8000 + edges kept only on
 * the first fragment) this real file must produce exactly ONE chunk under the
 * wire limit. Assertions target behavior, not logger calls.
 */
import '@/utils/mastra-rag.test-utils';

import * as fs from 'fs/promises';
import * as path from 'path';
import { DEFAULT_CONTENT_FILTER_OPTIONS } from '../../application/services/content-classifier.service';
import { ContentChunk, FILE_ROLES } from '../../domain/content-chunk.entity';
import { SessionMetadata } from '../../domain/session-metadata.type';
import { FIXTURES_DIR } from '../../e2e/e2e-utils';
import { ConfigurationService } from '../../infrastructure/config/configuration.service';
import {
  EnhancementPipelineService,
} from '../services/enhancement-pipeline.service';
import { SessionMetadataService } from '../../infrastructure/services/session-metadata.service';
import { SOURCE_TYPES } from '../../infrastructure/config/source-types';
import { WatchSourceConfig } from '../../infrastructure/config/config-schemas';
import { BasePinoLogger } from '../../infrastructure/logging/base-pino-logger';
import { RememberRequestSerializer } from '../../infrastructure/mnemosyne/remember-request.serializer';
import { Result } from '../../utils/result';
import { AgentPersonaChunkingStrategy } from './agent-persona-chunking.strategy';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { EdgeDistributionService } from './edge-distribution.service';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';
import { StrategyRouter } from './strategy-router.service';
import { VaultChunkingStrategy } from './vault-chunking.strategy';
import { ChunkContentUseCase } from '../../use-cases/chunk-content.use-case';

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

// --- Fixture paths ---

const PERSONA_FIXTURE_DIR = path.join(FIXTURES_DIR, 'agent-persona-threads-operator');
const PERSONA_ENTRY_PATH = path.join(PERSONA_FIXTURE_DIR, '00-entry.md');
const CONFIG_FIXTURE_PATH = path.join(FIXTURES_DIR, 'agent-persona-config.yaml');

describe('AgentPersonaChunkingStrategy through real ChunkContentUseCase — single chunk from threads-operator entry', () => {
  let logger: BasePinoLogger;
  let router: StrategyRouter;
  let configurationService: ConfigurationService;
  let useCase: ChunkContentUseCase;
  let mastra: jest.Mocked<MastraChunkingService>;

  const WIRE_LIMIT = 8000;

  beforeEach(async () => {
    jest.clearAllMocks();
    logger = createMockLogger();
    mastra = createMockMastraChunkingService([createBodyChunk('mastra fallback body')]);

    const edgeDistribution = new EdgeDistributionService(logger);
    const sessionMetadataService = {
      extract: jest.fn().mockResolvedValue(
        okResult<SessionMetadata>({
          sessionId: 'ses_integration-persona',
          createdAt: '2026-09-29T00:00:00Z',
        }),
      ),
    } as unknown as SessionMetadataService;

    const agentSessionStrategy = new AgentSessionChunkingStrategy(
      sessionMetadataService,
      mastra,
      edgeDistribution,
      logger,
    );
    const obsidianStrategy = new ObsidianChunkingStrategy(mastra, logger);
    const vaultStrategy = new VaultChunkingStrategy(mastra, logger);
    const personaStrategy = new AgentPersonaChunkingStrategy(logger);

    router = new StrategyRouter(
      agentSessionStrategy,
      obsidianStrategy,
      mastra,
      vaultStrategy,
      personaStrategy,
      logger,
    );

    configurationService = new ConfigurationService(logger, CONFIG_FIXTURE_PATH);
    const loadResult = await configurationService.load();
    expect(loadResult.isOk()).toBe(true);

    // skipEnrichment path never touches the enhancement pipeline; a stub keeps
    // the test hermetic (importance/tag scoring would need no network anyway).
    const enhancementPipeline = {
      enhance: jest.fn(),
    } as unknown as EnhancementPipelineService;

    useCase = new ChunkContentUseCase(router, enhancementPipeline, configurationService, logger);
  });

  it('emits exactly ONE chunk from 00-entry.md, under the 8000-byte request limit, with its decision edges intact', async () => {
    const content = await fs.readFile(PERSONA_ENTRY_PATH, 'utf-8');

    const sourceConfig: WatchSourceConfig = {
      id: 'agent-persona_threads-operator',
      path: PERSONA_FIXTURE_DIR,
      memoryBank: 'agent-persona_threads-operator',
      exclude: [],
      debounceMs: 3000,
      sourceType: SOURCE_TYPES.AGENT_PERSONA,
      contentFilter: DEFAULT_CONTENT_FILTER_OPTIONS,
      autoPopulate: true,
    };

    const result = await useCase.execute({
      content,
      filePath: PERSONA_ENTRY_PATH,
      sourceId: sourceConfig.id,
      memoryBank: sourceConfig.memoryBank,
      sourceConfig,
      skipEnrichment: true,
    });

    expect(result.isOk()).toBe(true);
    const chunks = result.getValue();

    // THE regression assertion: one logical node ⇒ one chunk. The old clamp
    // exploded this file into hundreds of near-empty fragments.
    expect(chunks.length).toBe(1);

    const chunk = chunks[0];
    expect(chunk.chunkIndex).toBe(0);
    expect(chunk.totalChunks).toBe(1);

    // The single chunk must fit the configured wire limit (the 405 guard).
    const serialized = new RememberRequestSerializer().buildAndSerialize(chunk);
    const serializedBytes = Buffer.byteLength(serialized, 'utf8');
    expect(serializedBytes).toBeLessThanOrEqual(WIRE_LIMIT);

    // The persona decision/hierarchy envelope survived exactly once.
    const edges = chunk.edges ?? [];
    expect(edges.length).toBeGreaterThan(0);
    expect(edges.every(e => typeof e.target_path === 'string')).toBe(true);

    // Text is faithful — the full entry body is present, not a 2-char stub.
    expect(chunk.text).toContain('Enter: load grounding and navigator skill, resolve target');

    // sourceType stamped end-to-end (D29).
    expect(chunk.metadata?.sourceType).toBe(SOURCE_TYPES.AGENT_PERSONA);
  });
});
