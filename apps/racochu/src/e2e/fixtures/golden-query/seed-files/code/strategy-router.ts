/**
 * Chunking strategy router — selects the appropriate chunking strategy
 * based on the watch source configuration.
 */

import { Injectable, Logger } from '@nestjs/common';
import { MastraChunkingService } from './mastra-chunking.service';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';

export interface ChunkingStrategy {
  chunkFile(content: string, filePath: string): Promise<string[]>;
}

@Injectable()
export class StrategyRouter {
  private readonly logger = new Logger(StrategyRouter.name);

  constructor(
    private readonly mastra: MastraChunkingService,
    private readonly agentSessions: AgentSessionChunkingStrategy,
    private readonly obsidian: ObsidianChunkingStrategy,
  ) {}

  /**
   * Routes to the correct chunking strategy based on source config.
   * - 'agent-sessions' → AgentSessionChunkingStrategy
   * - 'obsidian' → ObsidianChunkingStrategy
   * - default → content-aware MastraChunkingService
   */
  resolve(strategy?: string): ChunkingStrategy {
    switch (strategy) {
      case 'agent-sessions':
        return this.agentSessions;
      case 'obsidian':
        return this.obsidian;
      default:
        this.logger.debug('Using content-aware Mastra chunking strategy');
        return this.mastra;
    }
  }
}
