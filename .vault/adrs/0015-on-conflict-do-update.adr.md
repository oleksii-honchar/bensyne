---
type: adr
id: ADR-0015
title: "Safe File Upserts — session.merge() over INSERT OR REPLACE (SQLAlchemy ORM)"
status: accepted
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T16:58:00Z"
tags: [sqlite, upsert, file-metadata, gotcha]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0005-sqlite-hash-index.adr.md"
  - "memories/0005-on-conflict-do-update.memory.md"
---

# ADR-0015: Safe File Upserts — session.merge() over INSERT OR REPLACE

## Context

File upserts in `FileRepository.save_file()` need to handle the case where a file with the same ID already exists. The initial implementation used `INSERT OR REPLACE`, which caused file_chunks to be orphaned on file update due to `ON DELETE CASCADE` on the `file_chunks` foreign key.

## Decision

Use SQLAlchemy `session.merge()` for file upserts (previously raw `INSERT ... ON CONFLICT(id) DO UPDATE SET ...`). The ORM `merge()` updates the file row in-place without triggering DELETE CASCADE on related file_chunks — same safety property as `ON CONFLICT DO UPDATE`, expressed through the ORM.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| **session.merge() (chosen)** | ORM-native, updates in-place, no cascade | Slightly more verbose | — |
| **INSERT OR REPLACE (initial)** | Simpler syntax | Deletes + re-inserts, triggers ON DELETE CASCADE | Loses associated file_chunks |
| **SELECT then INSERT/UPDATE** | Explicit control | Race condition risk, more queries | Unnecessary complexity |

## Consequences

- **Positive:** File updates preserve associated chunks, no data loss
- **Negative:** None identified
- **Neutral:** Applies to all SQLAlchemy upserts in bensyne — established as the pattern for future repositories
