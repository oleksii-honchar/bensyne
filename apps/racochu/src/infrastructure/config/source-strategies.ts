import { ValuesType } from '@/utils/values-type';

export const SOURCE_STRATEGIES = {
  AGENT_SESSIONS: 'agent-sessions',
  OBSIDIAN: 'obsidian',
  CONTENT_AWARE: 'content-aware',
} as const;

export type SourceStrategy = ValuesType<typeof SOURCE_STRATEGIES>;

export const StrategyDescriptions: Record<SourceStrategy, string> = {
  [SOURCE_STRATEGIES.AGENT_SESSIONS]: 'Optimized for agent session files with structured metadata',
  [SOURCE_STRATEGIES.OBSIDIAN]: 'Optimized for Obsidian vault notes with backlinks and frontmatter',
  [SOURCE_STRATEGIES.CONTENT_AWARE]: 'Adapts chunking strategy based on detected content type',
};
