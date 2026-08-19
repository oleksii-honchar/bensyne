---
type: concept
system: racochu
title: "Chunking Strategy Pattern"
createdAt: "2026-08-06T12:00:00Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [architecture, chunking, strategy, design-pattern]
see_also: [decisions/0034-custom-chunking-strategies-framework.decision.md, decisions/0051-vault-chunking-strategy.decision.md, concepts/0013-mastra-chunking-strategies.concept.md, concepts/0024-vault-note-chunking.concept.md]
---

# Concept: Chunking Strategy Pattern

## What

A source-kinded strategy selection pattern that routes chunking requests to the appropriate strategy based on the watch source's configured `strategy` field. The `ChunkingStrategy` interface defines a common contract, and `StrategyRouter` selects the implementation at runtime.

## Why

Different source kinds require fundamentally different chunking behaviors. Agent sessions need parent-file metadata enrichment; Obsidian notes need frontmatter extraction with tag merging; vaults need wikilink edge vocabulary and a resolution ladder; generic files just need extension-based Mastra chunking. A single strategy cannot serve all.

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
    case 'vault': return this.vaultStrategy
    case 'content-aware':
    default: return this.mastraStrategy
  }
}
```

**SourceStrategies (verified in `src/infrastructure/config/source-types.ts`):**

| Constant | Value | Description |
|----------|-------|-------------|
| `AGENT_SESSIONS` | `agent-sessions` | Session-aware chunking with metadata enrichment from session.md |
| `OBSIDIAN` | `obsidian` | Obsidian note-aware chunking with frontmatter extraction and note metadata |
| `VAULT` | `vault` | Vault note-aware chunking — Obsidian vaults with `_index.md` skip, wikilink edges, 6-level resolution ladder |
| `CONTENT_AWARE` | `content-aware` | Content-aware generic chunking (default) — splits by semantic boundaries |

**WatchSource entity (verified in `src/domain/watch-source.entity.ts`):**
- `strategy` field: `z.string().min(1).default('content-aware')` — defaults to Mastra content-aware chunking
