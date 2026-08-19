---
type: decision
id: DEC-0056
system: racochu
title: "Reuse NoteMetadata for Vault Nodes with Vault-Aware Key Mapping"
status: accepted
createdAt: "2026-08-19T18:44:41Z"
updatedAt: "2026-08-19T18:44:41Z"
tags: [chunking, vault, metadata, note-metadata]
supersedes: []
superseded_by: []
see_also: [decisions/0035-obsidian-note-chunking-strategy.decision.md, decisions/0044-generic-frontmatter-preservation.decision.md, concepts/0018-obsidian-note-chunking.concept.md, concepts/0024-vault-note-chunking.concept.md]
---

# DEC-0056: Reuse NoteMetadata for Vault Nodes

## Context

Obsidian strategy owns the `NoteMetadata` type + `formatNoteMetadata` (private). Vault
frontmatter uses different keys (`createdAt`/`updatedAt`/`system`/`id`/`title`/
`see_also` vs `created`/`modified`/`base`). Vault nodes are "notes" in the same sense —
one metadata convention should serve both.

## Decision

The vault strategy reuses the existing `NoteMetadata` type (no parallel type —
`properties` escape hatch covers vault-specific keys) with vault-aware mapping:
`createdAt→created`, `updatedAt→modified`, `type`/`status`/`tags` typed;
`id`/`system`/`title`/`see_also`/`supersedes`/`deprecated` → `properties`.
`formatNoteMetadata` gained `export` in `obsidian-chunking.strategy.ts` so both
strategies share the exact `note.*` key convention.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| New `VaultNodeMetadata` type | Parallel type for the same concept; consumers see two shapes for "note metadata" |
| Duplicate the formatter into vault strategy | Drift risk between two `note.*` conventions |
| Move both formatters to strategy-utils | Bigger refactor for one consumer; revisit if a third note-like strategy appears |

## Consequences

- **Positive:** One metadata convention across note-like strategies; minimal diff.
- **Negative:** Slight cross-strategy import for one pure function — acceptable at this scale.
