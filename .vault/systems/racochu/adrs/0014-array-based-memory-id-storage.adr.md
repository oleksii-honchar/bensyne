---
type: adr
id: ADR-0014
title: "Array-Based Memory ID Storage"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [data-model, prisma]
see_also: ["adrs/0010-file-memory-tracking-prisma-sqlite.adr.md", "concepts/0007-file-memory-tracking.concept.md"]
---

# ADR-0014: Array-Based Memory ID Storage

## Context
Need to store multiple memory IDs per file in the Prisma schema.

## Decision
Store memory IDs as a JSON array in a single field per file.

## Rationale
1. **Simplicity** — Single row per file, no joins
2. **Performance** — One query to get all memory IDs
3. **Schema alignment** — Matches the mental model (one file → many memories)
4. **Prisma support** — Native array field support in SQLite

## Alternatives Considered
1. **Separate rows** — More normalized but requires joins
2. **String concatenation** — Manual parsing, error-prone
3. **JSON blob** — Less structured than array

## Consequences
- **Positive**: Simple queries, good performance
- **Negative**: Array operations can be slow for very large arrays
- **Mitigation**: Arrays should be small (typically <100 memories per file)
