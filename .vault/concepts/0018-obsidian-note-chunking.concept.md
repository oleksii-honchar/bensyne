---
type: concept
system: racochu
title: "Obsidian Note Chunking"
createdAt: "2026-08-06T12:00:00Z"
updatedAt: "2026-08-08T13:55:00Z"
tags: [chunking, obsidian, metadata]
see_also: [concepts/0016-chunking-strategy-pattern.concept.md, decisions/0035-obsidian-note-chunking-strategy.decision.md, decisions/0044-generic-frontmatter-preservation.decision.md, decisions/0045-wikilink-extraction-graph-structure.decision.md]
---

# Concept: Obsidian Note Chunking

## What

A chunking strategy specific to Obsidian notes that extracts YAML frontmatter as a separate chunk, enriches all body chunks with note-specific metadata, and parses body `[[wikilinks]]` into graph metadata. Frontmatter includes typed fields (aliases, tags, created, modified, source, status, type, base) plus all remaining keys as generic `properties`. Tags from Obsidian frontmatter are merged into each body chunk's tags array.

## Why

Obsidian notes carry rich metadata in frontmatter that improves retrieval quality. Without extraction, frontmatter is treated as body text — the metadata is lost as structured information. With tag merging, Obsidian tags become searchable attributes on all chunks from the note. With wikilink extraction, Obsidian graph edges become queryable metadata — any retrieved chunk exposes the note's full outlink set.

## Key Details

**Flow (verified in `src/application/strategies/obsidian-chunking.strategy.ts`):**

1. **Split frontmatter from body** — shared `splitFrontmatter` util
2. **Extract wikilinks from body** — `extractWikilinks(body)` (body-derived, independent of frontmatter)
3. **Extract note metadata** — parses YAML frontmatter via `yaml.load()`, typed keys to explicit fields, remaining keys to `properties`
4. **Create frontmatter chunk** — `importance: 0.9`, tags `['frontmatter', 'metadata', 'obsidian-note']`
5. **Chunk body with Mastra** — delegates to `MastraChunkingService`
6. **Enrich all chunks** — injects note metadata as `note.*` keys; merges Obsidian tags into chunk tags; attaches wikilinks

**Note metadata format (verified in `src/domain/note-metadata.type.ts`):**

| Field | Type | Example |
|-------|------|---------|
| `aliases` | `string[]` | `["billing-cycle", "billing-period"]` |
| `tags` | `string[]` | `["#billing", "#finance", "#adr"]` |
| `created` | `string` | `2026-07-15` |
| `modified` | `string` | `2026-08-05` |
| `source` | `string` | `https://example.com` |
| `status` | `string` | `draft` |
| `type` | `string` | `note` |
| `base` | `string` | `[[Database Name]]` (Obsidian database link) |
| `properties` | `Record<string, string>` | `{ "notion-id": "abc123", "kind": "meeting" }` (all remaining keys, lowercased) |

**Injected metadata keys:**

| Key | Value |
|-----|-------|
| `note.aliases` | JSON.stringify(metadata.aliases) |
| `note.tags` | JSON.stringify(metadata.tags) |
| `note.created` | metadata.created |
| `note.modified` | metadata.modified |
| `note.source` | metadata.source |
| `note.status` | metadata.status |
| `note.type` | metadata.type |
| `note.base` | metadata.base (raw Obsidian database link) |
| `note.properties.<key>` | stringified value for each remaining frontmatter key |
| `note.wikilinks` | JSON.stringify(wikilinks) (body-derived graph edges) |

**Wikilink extraction (verified in `src/utils/strategy-utils.ts`):**

- `extractWikilinks(text: string): string[]` — pure function, no dependencies
- Regex: `/\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]/g`
- Coverage: `[[Note]]`, `[[Note|alias]]`, `[[Note#Section]]`, `[[Note#Section|alias]]`, `![[embed]]`
- Dedup preserving first-occurrence order; no cap on count
- Attached to all chunks regardless of frontmatter presence (body-derived)

**Key difference from agent sessions:**
- Obsidian: metadata comes from same-file frontmatter; no parent file lookup; tags are merged into chunk tags
- Agent sessions: metadata comes from parent `session.md`; no tag merging; metadata is session-scoped

**Config example:**

```yaml
watchSources:
  - id: obsidian-vault
    path: ~/obsidian
    strategy: obsidian
    memoryBank: obsidian
    description: "Obsidian vault notes — personal knowledge base"
    exclude:
      - '.git/**'
      - 'node_modules/**'
    debounceMs: 5000
```
