import '@/utils/mastra-rag.test-utils';

import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import { SOURCE_STRATEGIES } from '@/infrastructure/config/source-strategies';
import { aLogger } from '@/infrastructure/logging/logger.test-utils';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';
import { StrategyRouter } from './strategy-router.service';

describe('StrategyRouter', () => {
  let router: StrategyRouter;
  let mockAgentSessionStrategy: jest.Mocked<AgentSessionChunkingStrategy>;
  let mockObsidianStrategy: jest.Mocked<ObsidianChunkingStrategy>;
  let mockMastraStrategy: jest.Mocked<MastraChunkingService>;
  let mockLogger: ReturnType<typeof aLogger>;

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

  describe('selectStrategy', () => {
    it('should return AgentSessionChunkingStrategy for agent-sessions strategy', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.AGENT_SESSIONS,
      };

      const result = router.selectStrategy(sourceConfig);

      expect(result).toBe(mockAgentSessionStrategy);
    });

    it('should return ObsidianChunkingStrategy for obsidian strategy', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.OBSIDIAN,
      };

      const result = router.selectStrategy(sourceConfig);

      expect(result).toBe(mockObsidianStrategy);
    });

    it('should return MastraChunkingService for content-aware strategy', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
      };

      const result = router.selectStrategy(sourceConfig);

      expect(result).toBe(mockMastraStrategy);
    });

    it('should return MastraChunkingService as default for unknown strategy', () => {
      // Simulate an unknown strategy value by casting
      const sourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: 'unknown-strategy' as unknown as WatchSourceConfig['strategy'],
      };

      const result = router.selectStrategy(sourceConfig);

      expect(result).toBe(mockMastraStrategy);
    });

    it('should return MastraChunkingService when strategy is content-aware (default)', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
      };

      const result = router.selectStrategy(sourceConfig);

      expect(result).toBe(mockMastraStrategy);
    });

    it('should throw error when strategy resolves to undefined', () => {
      const routerWithUndefinedStrategy = new StrategyRouter(
        mockAgentSessionStrategy,
        undefined as unknown as ObsidianChunkingStrategy,
        undefined as unknown as MastraChunkingService,
        mockLogger,
      );

      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.OBSIDIAN,
      };

      expect(() => routerWithUndefinedStrategy.selectStrategy(sourceConfig)).toThrow(
        'No chunking strategy available for strategy="obsidian", sourceId="test"',
      );
    });

    it('should log strategy resolution', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.OBSIDIAN,
      };

      router.selectStrategy(sourceConfig);

      expect(mockLogger.debug).toHaveBeenCalledWith(
        expect.stringContaining('Strategy selected: strategy="obsidian", sourceId="test"'),
      );
    });

    it('should log strategy resolution for fallback (content-aware)', () => {
      const sourceConfig: WatchSourceConfig = {
        id: 'test',
        path: '/test',
        memoryBank: 'test',
        exclude: [],
        debounceMs: 3000,
        strategy: SOURCE_STRATEGIES.CONTENT_AWARE,
      };

      router.selectStrategy(sourceConfig);

      expect(mockLogger.debug).toHaveBeenCalledWith(
        expect.stringContaining('Strategy selected: strategy="content-aware", sourceId="test"'),
      );
    });
  });
});
