---
type: concept
title: "Chunking Strategy Pattern"
createdAt: "2026-08-06T12:00:00Z"
updatedAt: "2026-08-06T12:00:00Z"
tags: [architecture, chunking, strategy, design-pattern]
see_also: ["adrs/0016-custom-chunking-strategies-framework.adr.md", "concepts/0006-mastra-chunking-strategies.concept.md"]
---

# Concept: Chunking Strategy Pattern

## What

A source-kinded strategy selection pattern that routes chunking requests to the appropriate strategy based on the watch source's configured `strategy` field. The `ChunkingStrategy` interface defines a common contract, and `StrategyRouter` selects the implementation at runtime.

## Why

Different source kinds require fundamentally different chunking behaviors. Agent sessions need parent-file metadata enrichment; Obsidian notes need frontmatter extraction with tag merging; generic files just need extension-based Mastra chunking. A single strategy cannot serve all.

## Key Details

**Interface (verified in `src/application/strategies/agent-session-chunking.strategy.ts`):**

```typescript
interface ChunkingStrategy {
  chunkFile(
    content: string,
    filePath: string,
    sourceId: string,
    sourceConfig: WatchSourceConfig,
  ): Promise<Result<ContentChunk[]>>
}
```

**StrategyRouter (verified in `src/application/strategies/strategy-router.service.ts`):**

```typescript
selectStrategy(sourceConfig: WatchSourceConfig): ChunkingStrategy {
  switch (sourceConfig.strategy) {
    case 'agent-sessions': return this.agentSessionStrategy
    case 'obsidian': return this.obsidianStrategy
    case 'content-aware':
    default: return this.mastraStrategy
  }
}
```

**SourceStrategies (verified in `src/infrastructure/config/source-strategies.ts`):**

| Constant | Value | Description |
|----------|-------|-------------|
| `AGENT_SESSIONS` | `agent-sessions` | Session-aware chunking with metadata enrichment from session.md |
| `OBSIDIAN` | `obsidian` | Obsidian note-aware chunking with frontmatter extraction and note metadata |
| `CONTENT_AWARE` | `content-aware` | Content-aware generic chunking (default) — splits by semantic boundaries |

**WatchSource entity (verified in `src/domain/watch-source.entity.ts`):**
- `strategy` field: `z.string().min(1).default('content-aware')` — defaults to Mastra content-aware chunking
