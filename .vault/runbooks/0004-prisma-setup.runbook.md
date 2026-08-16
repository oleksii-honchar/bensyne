---
type: runbook
system: racochu
title: "Prisma SQLite Setup"
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [prisma, setup, operations]
see_also: [decisions/0028-file-memory-tracking-prisma-sqlite.decision.md]
---

# Runbook: Prisma SQLite Setup

## Purpose

Initialize and manage the Prisma SQLite database used for File→Memory tracking.

## Prerequisites

- Node.js 20+
- Project dependencies installed (`npm install`)
- `data/` directory exists

## Steps

1. **Generate Prisma client:**
   ```bash
   npx prisma generate
   ```
   Output: `src/generated/prisma/`

2. **Apply schema to database:**
   ```bash
   npx prisma db push
   ```
   Creates `data/file_memory.db` with `FileTracker` and `FileMemoryTracker` tables.

3. **Verify:**
   ```bash
   npx prisma studio
   ```
   Opens browser UI at localhost:5555 — should show empty `FileTracker` and `FileMemoryTracker` tables.

## Schema Reference

**Tables:**
- `FileTracker` — id, filePath (unique), sourceId, namespace, createdAt, updatedAt
- `FileMemoryTracker` — id, memoryId, fileTrackerId (FK), createdAt, updatedAt

## Rollback

- Delete database: `rm data/file_memory.db`
- Re-apply schema: `npx prisma db push`

## Notes

- Database is local to RAG Content Chunker instance
- No production migrations needed — schema changes via `db push`
- SQLite does not support `@db.Text` — use `String` (maps to TEXT by default)
