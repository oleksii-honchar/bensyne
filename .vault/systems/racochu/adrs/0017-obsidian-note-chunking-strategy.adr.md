---
type: adr
id: ADR-0017
title: "Obsidian Note Chunking Strategy"
status: accepted
createdAt: "2026-08-05T18:31:00Z"
updatedAt: "2026-08-05T18:31:00Z"
tags: [chunking, obsidian, strategy]
supersedes: []
superseded_by: []
see_also: ["adrs/0016-custom-chunking-strategies-framework.adr.md", "concepts/0011-obsidian-note-chunking.concept.md"]
---

# ADR-0017: Obsidian Note Chunking Strategy

## Context

Obsidian notes contain YAML frontmatter with note-specific metadata (aliases, tags, created, modified, source, etc.). This frontmatter should be extracted as a separate chunk and the metadata should enrich all chunks from the note. Unlike agent sessions, Obsidian frontmatter belongs to a single file only — no parent file lookup needed.

## Decision

Implement an `obsidian` chunking strategy that:
1. Extracts frontmatter as a separate chunk
2. Parses note-specific metadata from the frontmatter
3. Enriches all chunks with note metadata (aliases, tags merged into chunk tags)

```yaml
watchSources:
  - id: obsidian-vault
    path: ~/obsidian
    strategy: obsidian
    memoryBank: obsidian
```

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Generic frontmatter strategy | One strategy handles all | Different metadata extraction per source kind | Rejected: different semantics |
| Enhance content-aware strategy | Minimal code | Pollutes generic chunking | Rejected: separation of concerns |
| No strategy (content-aware only) | Simplest | Frontmatter treated as body text | Rejected: loses metadata structure |

## Consequences

- **Positive:** Clean separation from agent-session strategy. Frontmatter available as searchable chunk. Tags from Obsidian notes propagate to all body chunks.
- **Negative:** Additional strategy to maintain and test.
- **Mitigation:** Thin interface, reuses Mastra for body chunking.
