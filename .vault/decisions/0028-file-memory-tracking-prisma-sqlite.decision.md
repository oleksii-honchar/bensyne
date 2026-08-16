---
type: decision
id: DEC-0028
system: racochu
title: "File→Memory Tracking with Prisma SQLite"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [infrastructure, data-model]
see_also: [concepts/0014-file-memory-tracking.concept.md]
---

# DEC-0028: File→Memory Tracking with Prisma SQLite

## Context
When files are deleted or updated in watched directories, we need to update or delete corresponding memories in Mnemosyne. Currently, no mapping exists between file paths and memory IDs.

## Decision
Add Prisma SQLite to RAG Content Chunker for local file→memory relationship tracking.

## Rationale
1. **Reliability** — Direct memory ID lookup by file path is more reliable than semantic recall
2. **Performance** — SQLite lookup is O(1) vs O(n) for semantic search
3. **Completeness** — Guarantees all memories are cleaned up on file deletion
4. **Type Safety** — Prisma provides compile-time type checking

## Alternatives Considered
1. **JSON file mapping** — Simpler but lacks type safety and concurrent access support
2. **Semantic recall for cleanup** — Less reliable, may miss or delete wrong memories
3. **No tracking** — Memories persist after file deletion (current state)

## Consequences
- **Positive**: Reliable memory cleanup, type-safe queries
- **Negative**: Additional dependency (Prisma), local database to maintain
- **Mitigation**: Minimal schema, well-documented Prisma setup
