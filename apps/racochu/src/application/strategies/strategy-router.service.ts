import { WatchSourceConfig } from '@/infrastructure/config/config-schemas';
import {
  SOURCE_TYPES,
  SOURCE_TYPE_UNKNOWN,
  sourceTypeSchema,
  WireSourceType,
} from '@/infrastructure/config/source-types';
import { BasePinoLogger } from '@/infrastructure/logging/base-pino-logger';
import { Injectable } from '@nestjs/common';
import { AgentSessionChunkingStrategy } from './agent-session-chunking.strategy';
import { BaseChunkingStrategy } from './base-chunking-strategy';
import { MastraChunkingService } from './mastra-chunking.service';
import { ObsidianChunkingStrategy } from './obsidian-chunking.strategy';

/**
 * Routes chunking requests to the appropriate chunker based on the watch
 * source's `sourceType` field (D29: the field IS the source type).
 *
 * Routing (source_type → chunker):
 *   obsidian        → ObsidianChunkingStrategy
 *   agent-sessions  → AgentSessionChunkingStrategy
 *   vault           → MastraChunkingService (content-aware path, re-keyed)
 *   unknown / other → MastraChunkingService (fallback)
 *
 * Degrade-never-reject (mirrors bensyne `_coerce_source_type`): any incoming
 * source type is resolved onto the 4-value axis (`obsidian | agent-sessions |
 * vault | unknown`) and never throws — off-axis values resolve to `unknown`.
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

  /**
   * Resolves any incoming source type onto the 4-value wire axis
   * (`obsidian | agent-sessions | vault | unknown`). Off-axis or missing values
   * degrade to `unknown` — never throws (bensyne `_coerce_source_type` parity).
   */
  resolveSourceType(sourceType: string | undefined): WireSourceType {
    if (sourceType === undefined) {
      return SOURCE_TYPE_UNKNOWN;
    }
    const parsed = sourceTypeSchema.safeParse(sourceType);
    return parsed.success ? parsed.data : SOURCE_TYPE_UNKNOWN;
  }

  selectStrategy(sourceConfig: WatchSourceConfig): BaseChunkingStrategy {
    const sourceType = this.resolveSourceType(sourceConfig.sourceType);

    const map: Record<WireSourceType, BaseChunkingStrategy> = {
      [SOURCE_TYPES.OBSIDIAN]: this.obsidianStrategy,
      [SOURCE_TYPES.AGENT_SESSIONS]: this.agentSessionStrategy,
      [SOURCE_TYPES.VAULT]: this.mastraStrategy,
      [SOURCE_TYPE_UNKNOWN]: this.mastraStrategy,
    };

    // Degrade-never-reject: an off-axis type resolves to unknown ⇒ Mastra
    // fallback; a missing chunker binding degrades the same way. Never throws.
    const chunker = map[sourceType] ?? this.mastraStrategy;

    this.logger.debug(
      `Chunker selected: sourceType="${sourceConfig.sourceType}", resolved="${sourceType}", sourceId="${sourceConfig.id}", chunker="${chunker.constructor.name}"`,
    );

    return chunker;
  }
}
