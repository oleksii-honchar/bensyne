---
type: adr
id: ADR-0036
title: "Wikilink Extraction for Graph Structure"
status: accepted
createdAt: "2026-08-08T13:55:00Z"
updatedAt: "2026-08-08T13:55:00Z"
tags: [obsidian, wikilinks, graph, metadata, chunking]
supersedes: []
superseded_by: []
see_also: ["adrs/0026-generic-frontmatter-preservation.adr.md", "adrs/0017-obsidian-note-chunking-strategy.adr.md", "concepts/0011-obsidian-note-chunking.concept.md"]
---

# ADR-0036: Wikilink Extraction for Graph Structure

## Context

Obsidian notes connect via internal `[[wikilinks]]` (graph edges). The strategy never parsed them — body content with links was passed raw to Mastra, so graph structure was absent from memory.

## Decision

Add a pure function `extractWikilinks(text: string): string[]` in `src/utils/strategy-utils.ts`:

- Regex `/\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]/g` captures target before `#` (heading) and `|` (alias)
- Handles `[[Note]]`, `[[Note|alias]]`, `[[Note#Section]]`, `[[Note#Section|alias]]`, `![[embed]]`
- Dedup preserving first-occurrence order (no cap)
- Result injected as `note.wikilinks: JSON.stringify(links)` on all chunks when non-empty

Wikilinks are body-derived and kept OUT of `NoteMetadata` (frontmatter-only type). No new dependency — regex-based extraction.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Parse in `extractNoteMetadata` | Single extraction point | Blurs frontmatter/body separation | Rejected: NoteMetadata is frontmatter-only |
| Dedicated wikilink service | Extensible | No state needed | Rejected: over-engineering for a regex |
| Pure util + strategy wiring (CHOSEN) | Testable, reusable | New function to maintain | Accepted |

## Consequences

- **Positive:** Graph edges become queryable metadata on every chunk of the note; strategy description "backlinks and frontmatter" becomes accurate.
- **Negative:** Regex misses exotic link syntax variants (e.g. escaped brackets); metadata grows by one key.
- **Mitigation:** Unit tests cover standard variants; dedup bounds size.
