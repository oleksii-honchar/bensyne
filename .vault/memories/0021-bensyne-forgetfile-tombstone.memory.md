---
type: memory
title: "Bensyne forgetFile Leaves a DELETED Tombstone — Not a Hard Row Delete"
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: shared
tags: [bensyne, forget, tombstone, gotcha]
see_also: ["decisions/0078-ttl-tombstone-acceptance.decision.md", "specifications/0006-source-ttl-sweep.spec.md"]
---

# Fact: Bensyne forgetFile Leaves a DELETED Tombstone — Not a Hard Row Delete

`forgetFile` (via `file_service.delete_file`) marks the bensyne `files` row
`status = 'deleted'` (tombstone) and cascades away its
`file_chunks`/`file_relations` — it does **not** hard-delete the row. The hard
`session.delete` repository path is unused on the forget path.

## Context

Discovered during the Source TTL feature (external review finding F1; accepted
in DEC-0079). Every forget — manual, `handleDelete`, exclude reconciliation,
TTL sweep — leaves a tombstone.

## Impact

`files` rows accumulate ~1y-of-ingest per year under TTL. This is existing
forget semantics (not introduced by TTL). If growth becomes observable, a
bensyne-side tombstone-purge sweep (query + batch delete of DELETED rows) is
the follow-up — but that requires a bensyne-mcp change.
