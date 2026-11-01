---
type: runbook
system: racochu
title: "Prisma SQLite Setup"
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [prisma, setup, operations]
see_also: [decisions/0028-file-memory-tracking-prisma-sqlite.decision.md, decisions/0120-prisma-migrate-deploy-with-fail-loud-dedup-guard.decision.md, memories/0030-better-sqlite3-napi-loads-node24-and-26.memory.md]
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

---

## Update 2026-11-01 — committed-migrations lifecycle replaces `db push` (DEC-0120)

- Startup schema management is now **`prisma migrate deploy`** against committed migrations
  (`prisma/migrations/0_init` baselined from the live schema; changes ship as additive
  migrations, e.g. `20261031_add_skip_reason`). The old per-startup
  `npx prisma db push --accept-data-loss` is retired (silent-wipe amplifier).
- **Pre-existing DBs:** mark the baseline once before first deploy:
  `npx prisma migrate resolve --applied 0_init` (metadata-only, no data touched).
- **Safety net:** `ensureSchema()` compares `FileTracker` row counts before/after the schema
  step and aborts startup on any decrease (`dedup state must not shrink …`). Fresh/empty DB is
  unaffected.
- Schema additions follow the additive-nullable-column pattern (DEC-0041) — never destructive
  renames in-place.
- Environment note: better-sqlite3 13.x is N-API (loads under Node 24 and 26) — see memory 0030;
  don't debug racochu DB failures via ABI theories.
