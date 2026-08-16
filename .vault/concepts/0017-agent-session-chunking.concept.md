---
type: concept
system: racochu
title: "Agent Session Chunking"
createdAt: "2026-08-06T12:00:00Z"
updatedAt: "2026-08-06T12:00:00Z"
tags: [chunking, agent-sessions, metadata]
see_also: [concepts/0016-chunking-strategy-pattern.concept.md, concepts/0019-session-metadata-service.concept.md, decisions/0034-custom-chunking-strategies-framework.decision.md]
---

# Concept: Agent Session Chunking

## What

A chunking strategy specific to agent session files that extracts YAML frontmatter as a separate chunk and enriches all chunks with metadata from the parent `session.md`. This enables session-scoped retrieval — all chunks from a session carry the `session.id` metadata key for filtering.

## Why

Agent session files (specs, decisions, plans, etc.) contain frontmatter with session-scoped metadata (sessionId, status, phase, nextAgent). Without enrichment, individual chunks lose their session context — semantic recall across sessions becomes noisy because chunks from different sessions are indistinguishable at the metadata level.

## Key Details

**Flow (verified in `src/application/strategies/agent-session-chunking.strategy.ts`):**

1. **Locate parent session.md** — walks up from the current file's directory to find `session.md`
2. **Extract session metadata** — via `SessionMetadataService` (cached, 5-min TTL)
3. **Split frontmatter from body** — regex: `/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/`
4. **Create frontmatter chunk** — if frontmatter exists, created as separate chunk with `importance: 0.9`, tags `['frontmatter', 'metadata']`
5. **Chunk body with Mastra** — delegates to `MastraChunkingService` for body content
6. **Enrich all chunks** — injects session metadata as `session.*` keys in chunk metadata

**Session metadata format (verified in `src/infrastructure/services/session-metadata.service.ts`):**

| Metadata Key | Source | Example |
|-------------|--------|---------|
| `session.id` | `sessionId` from session.md | `ses_057e2d847ffeJkvVN1hTxIim8L` |
| `session.createdAt` | `createdAt` from session.md | `2026-07-28T09:46:23Z` |
| `session.status` | `status` from session.md | `in-progress` |
| `session.phase` | `phase` from session.md | `implementation` |
| `session.nextAgent` | `nextAgent` from session.md | `vault-keeper` |

**Config example:**

```yaml
watchSources:
  - id: agent-sessions
    path: ~/.agent-sessions
    strategy: agent-sessions
    memoryBank: agent-sessions
    description: "Agent session files — research, specs, decisions, plans"
    exclude:
      - '**/archive/**'
      - '.smart-env/**'
    debounceMs: 5000
```
