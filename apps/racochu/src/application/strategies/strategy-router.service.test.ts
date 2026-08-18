import '@/utils/mastra-rag.test-utils';

import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import { SOURCE_TYPES, SOURCE_TYPE_UNKNOWN, WireSourceType } from '@/infrastructure/config/source-types';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';
import { StrategyRouter } from './strategy-router.service';

describe('StrategyRouter (D29: source_type → chunker)', () => {
  let router: StrategyRouter;
  let mockAgentSessionStrategy: jest.Mocked<AgentSessionChunkingStrategy>;
  let mockObsidianStrategy: jest.Mocked<ObsidianChunkingStrategy>;
  let mockMastraStrategy: jest.Mocked<MastraChunkingService>;
  let mockLogger: ReturnType<typeof aLogger>;

  const aSourceConfig = (sourceType: string): WatchSourceConfig =>
    ({
      id: 'test',
      path: '/test',
      memoryBank: 'test',
      exclude: [],
      debounceMs: 3000,
      sourceType,
    }) as unknown as WatchSourceConfig;

  beforeEach(() => {
    mockAgentSessionStrategy = {
      chunkFile: jest.fn(),
    } as unknown as jest.Mocked<AgentSessionChunkingStrategy>;

    mockObsidianStrategy = {
      chunkFile: jest.fn(),
    } as unknown as jest.Mocked<ObsidianChunkingStrategy>;

    mockMastraStrategy = {
      chunkFile: jest.fn(),
    } as unknown as jest.Mocked<MastraChunkingService>;

    mockLogger = aLogger();

    router = new StrategyRouter(
      mockAgentSessionStrategy,
      mockObsidianStrategy,
      mockMastraStrategy,
      mockLogger,
    );
  });

  describe('resolveSourceType (degrade-never-reject, mirrors bensyne _coerce_source_type)', () => {
    it.each(['obsidian', 'agent-sessions', 'vault', 'unknown'])(
      'resolves %s to itself (the 4-value axis)',
      sourceType => {
        expect(router.resolveSourceType(sourceType)).toBe(sourceType);
      },
    );

    it.each(['file_system', 'agent_session', 'git', 'database', 'external', 'remote', 'content-aware', 'garbage'])(
      'resolves legacy/unknown value %s to unknown (never throws)',
      sourceType => {
        expect(router.resolveSourceType(sourceType)).toBe(SOURCE_TYPE_UNKNOWN);
      },
    );

    it('resolves undefined input to unknown (never throws)', () => {
      expect(router.resolveSourceType(undefined)).toBe(SOURCE_TYPE_UNKNOWN);
    });
  });

  describe('selectStrategy — source_type → chunker dispatch', () => {
    it('dispatches obsidian to ObsidianChunkingStrategy', () => {
      const result = router.selectStrategy(aSourceConfig(SOURCE_TYPES.OBSIDIAN));

      expect(result).toBe(mockObsidianStrategy);
    });

    it('dispatches agent-sessions to AgentSessionChunkingStrategy', () => {
      const result = router.selectStrategy(aSourceConfig(SOURCE_TYPES.AGENT_SESSIONS));

      expect(result).toBe(mockAgentSessionStrategy);
    });

    it('dispatches vault to MastraChunkingService (content-aware path, re-keyed)', () => {
      const result = router.selectStrategy(aSourceConfig(SOURCE_TYPES.VAULT));

      expect(result).toBe(mockMastraStrategy);
    });

    it('resolves an unknown source_type to unknown and falls back to MastraChunkingService without throwing', () => {
      let result: BaseChunkingStrategy | undefined;

      expect(() => {
        result = router.selectStrategy(aSourceConfig('never-heard-of-it'));
      }).not.toThrow();

      expect(result).toBe(mockMastraStrategy);
    });

    it('never throws when a chunker binding is missing — degrades to the Mastra fallback', () => {
      const brokenRouter = new StrategyRouter(
        mockAgentSessionStrategy,
        undefined as unknown as ObsidianChunkingStrategy,
        mockMastraStrategy,
        mockLogger,
      );

      expect(() => brokenRouter.selectStrategy(aSourceConfig(SOURCE_TYPES.OBSIDIAN))).not.toThrow();
      expect(brokenRouter.selectStrategy(aSourceConfig(SOURCE_TYPES.OBSIDIAN))).toBe(mockMastraStrategy);
    });
  });

  describe('selectStrategy typing (return is a resolvable 4-value axis member)', () => {
    it('selectStrategy output type stays BaseChunkingStrategy', () => {
      const result: BaseChunkingStrategy = router.selectStrategy(aSourceConfig(SOURCE_TYPES.OBSIDIAN));

      expect(result).toBe(mockObsidianStrategy);
    });

    it('resolves the typed sourceType of a valid config verbatim', () => {
      const config = aSourceConfig(SOURCE_TYPES.AGENT_SESSIONS);
      const resolved: WireSourceType = router.resolveSourceType(config.sourceType);

      expect(resolved).toBe(SOURCE_TYPES.AGENT_SESSIONS);
    });
  });
});
