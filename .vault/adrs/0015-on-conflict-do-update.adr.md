---
type: adr
id: ADR-0015
title: "ON CONFLICT DO UPDATE for File Upserts (Not INSERT OR REPLACE)"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [sqlite, upsert, file-metadata, gotcha]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0005-sqlite-hash-index.adr.md"
  - "memories/0005-on-conflict-do-update.memory.md"
---

# ADR-0015: ON CONFLICT DO UPDATE for File Upserts (Not INSERT OR REPLACE)

## Context

File upserts in `FileRepositorySQLite.save_file()` need to handle the case where a file with the same ID already exists. The initial implementation used `INSERT OR REPLACE`, which caused file_chunks to be orphaned on file update due to `ON DELETE CASCADE` on the `file_chunks` foreign key.

## Decision

Use `INSERT ... ON CONFLICT(id) DO UPDATE SET ...` for file upserts. This updates the file row in-place without triggering DELETE CASCADE on related file_chunks.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **ON CONFLICT DO UPDATE (chosen)** | Updates in-place, no cascade | Slightly more verbose | — |
| **INSERT OR REPLACE (initial)** | Simpler syntax | Deletes + re-inserts, triggers ON DELETE CASCADE | Loses associated file_chunks |
| **SELECT then INSERT/UPDATE** | Explicit control | Race condition risk, more queries | Unnecessary complexity |

## Consequences

- **Positive:** File updates preserve associated chunks, no data loss
- **Negative:** None identified
- **Neutral:** Applies to all SQLite upserts in bensyne — established as the pattern for future repositories
