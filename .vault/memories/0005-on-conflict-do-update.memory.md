---
type: memory
title: "SQLite ON CONFLICT DO UPDATE (Not INSERT OR REPLACE)"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [sqlite, upsert, gotcha, file-metadata]
see_also:
  - "adrs/0015-on-conflict-do-update.adr.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# Memory: SQLite ON CONFLICT DO UPDATE (Not INSERT OR REPLACE)

## Fact

Use `INSERT ... ON CONFLICT(id) DO UPDATE SET ...` for upserts in SQLite, NOT `INSERT OR REPLACE`. The `INSERT OR REPLACE` pattern deletes and re-inserts, triggering `ON DELETE CASCADE` on foreign keys — this caused file_chunks to be orphaned on file update in `FileRepositorySQLite.save_file()`.

## Context

Discovered during the file metadata layer implementation. The initial implementation used `INSERT OR REPLACE` for file upserts. When a file was updated, the associated file_chunks were deleted via the `ON DELETE CASCADE` foreign key constraint, causing data loss. The fix was to use `INSERT ... ON CONFLICT(id) DO UPDATE SET ...` which updates the file row in-place without triggering cascades.

## Impact

- **Critical for all SQLite upserts** — applies to any table with foreign key references
- Established as the pattern for all future SQLite repositories in bensyne
- Documented as ADR-0015 and added to bensyne-specialist skill gotchas
