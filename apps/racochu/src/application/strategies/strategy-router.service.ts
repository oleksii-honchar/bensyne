import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import { SOURCE_STRATEGIES } from '@/infrastructure/config/source-strategies';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { Injectable } from '@nestjs/common';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';

/**
 * Routes chunking requests to the appropriate ChunkingStrategy
 * based on the sourceConfig.strategy field.
 *
 * Routing:
 *   agent-sessions  → AgentSessionChunkingStrategy
 *   obsidian        → ObsidianChunkingStrategy
 *   content-aware   → MastraChunkingService (default)
 *   unknown / other → MastraChunkingService (fallback)
 */
@Injectable()
export class StrategyRouter {
  private readonly logger: BasePinoLogger;

  constructor(
    private readonly agentSessionStrategy: AgentSessionChunkingStrategy,
    private readonly obsidianStrategy: ObsidianChunkingStrategy,
    private readonly mastraStrategy: MastraChunkingService,
    logger: BasePinoLogger,
  ) {
    this.logger = logger.child({ component: 'StrategyRouter' });
  }

  selectStrategy(sourceConfig: WatchSourceConfig): BaseChunkingStrategy {
    const map: Record<string, BaseChunkingStrategy> = {
      [SOURCE_STRATEGIES.AGENT_SESSIONS]: this.agentSessionStrategy,
      [SOURCE_STRATEGIES.OBSIDIAN]: this.obsidianStrategy,
    };

    const strategy = map[sourceConfig.strategy] ?? this.mastraStrategy;

    if (strategy === undefined) {
      this.logger.error(
        `No chunking strategy available for strategy="${sourceConfig.strategy}", sourceId="${sourceConfig.id}"`,
      );
      throw new Error(
        `No chunking strategy available for strategy="${sourceConfig.strategy}", sourceId="${sourceConfig.id}"`,
      );
    }

    this.logger.debug(
      `Strategy selected: strategy="${sourceConfig.strategy}", sourceId="${sourceConfig.id}", resolved="${strategy.constructor.name}"`,
    );

    return strategy;
  }
}
