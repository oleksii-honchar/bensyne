---
type: adr
id: ADR-0016
title: "Custom Chunking Strategies Framework"
status: accepted
createdAt: "2026-08-05T18:31:00Z"
updatedAt: "2026-08-05T18:31:00Z"
tags: [architecture, chunking, strategy, extensibility]
supersedes: []
superseded_by: []
see_also: ["concepts/0009-chunking-strategy-pattern.concept.md", "adrs/0009-mastra-rag-integration.adr.md", "adrs/0017-obsidian-note-chunking-strategy.adr.md"]
---

# ADR-0016: Custom Chunking Strategies Framework

## Context

After integrating Mastra RAG (ADR-0009), all files were chunked uniformly based on file extension. Agent session files require special handling: frontmatter extraction as a separate chunk, session metadata enrichment from parent `session.md`, and session-scoped retrieval. A generic content-aware strategy cannot accommodate these source-specific behaviors.

## Decision

Implement a **source-kinded strategy selection pattern** with:

1. **`ChunkingStrategy` interface** — defines `chunkFile(content, filePath, sourceId, sourceConfig)` contract
2. **`StrategyRouter`** — routes chunking requests to the appropriate strategy based on `sourceConfig.strategy`
3. **Three strategy implementations:**
   - `AgentSessionChunkingStrategy` — frontmatter extraction + session metadata enrichment
   - `ObsidianChunkingStrategy` — note frontmatter extraction + tag merging
   - `MastraChunkingService` — existing content-aware chunking (now implements `ChunkingStrategy`)
4. **Extended watch source config** — `strategy` field in `WatchSourceConfig` (enum: `agent-sessions`, `obsidian`, `content-aware`; defaults to `content-aware`)
5. **`SourceStrategies` constants** — type-safe strategy identifiers with descriptions

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Generic frontmatter strategy | One strategy handles all frontmatter | Different metadata extraction logic per source kind | Rejected: different semantics per source |
| Enhance content-aware strategy | Minimal new code | Pollutes generic chunking code with source-specific logic | Rejected: separation of concerns |
| Pre-processing pipeline | Decouples extraction from chunking | Adds pipeline complexity, metadata loss | Rejected: over-engineering |
| No framework, inline logic | Simplest | Tight coupling, hard to extend | Rejected: violates Open/Closed |

## Consequences

- **Positive:** Extensible — new strategies add a class, no existing code changes. Backward compatible — default `content-aware` strategy preserves current behavior.
- **Negative:** Additional abstraction layer adds a few lines of indirection. Each strategy needs its own test coverage.
- **Neutral:** MastraChunkingService now implements `ChunkingStrategy` — thin adapter, no behavioral change.
