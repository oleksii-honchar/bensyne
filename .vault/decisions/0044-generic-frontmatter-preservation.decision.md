---
type: decision
id: DEC-0044
system: racochu
title: "Generic Frontmatter Preservation with Typed base Field"
status: accepted
createdAt: "2026-08-08T13:55:00Z"
updatedAt: "2026-08-08T13:55:00Z"
tags: [obsidian, frontmatter, metadata, chunking]
supersedes: []
superseded_by: []
see_also: [decisions/0035-obsidian-note-chunking-strategy.decision.md, concepts/0018-obsidian-note-chunking.concept.md]
---

# DEC-0044: Generic Frontmatter Preservation with Typed base Field

## Context

`NoteMetadata` (DEC-0035) extracts only 7 known Obsidian frontmatter keys (`aliases, tags, created, modified, source, status, type`). Real notes carry arbitrary properties (`notion-id`, `Kind`, `Project`, `base`) that Obsidian databases use as columns/filters — these were silently dropped.

## Decision

Extend `NoteMetadata` (verified in `src/domain/note-metadata.type.ts`) with two fields:

1. `base: string` — raw frontmatter `base:` value (Obsidian database link), lossless
2. `properties: Record<string, string>` — ALL remaining frontmatter keys, lowercased, stringified

`extractNoteMetadata` (in `src/application/strategies/obsidian-chunking.strategy.ts`) iterates parsed frontmatter; keys matching `TYPED_KEYS` (`aliases, tags, created, modified, source, status, type, base`) are excluded from `properties` to avoid duplication. Metadata injected as `note.base` and `note.properties.<key>` via `formatNoteMetadata`.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Single JSON blob of all properties | One key | Not searchable per-key | Rejected: retrieval needs per-property keys |
| Flat merge into `note.*` | Simple | Collides with typed fields | Rejected: `note.created` vs `note.Created` ambiguity |
| Generic `properties` + typed `base` (CHOSEN) | Lossless + searchable + typed base | More metadata keys | Accepted: matches existing `note.*` convention |

## Consequences

- **Positive:** No frontmatter key lost; Obsidian database relationships emerge from preserved properties.
- **Negative:** More metadata keys per chunk; `NoteMetadata` construction sites must be updated.
- **Mitigation:** Compiler-enforced type change; additive keys keep stored chunks backward compatible.
