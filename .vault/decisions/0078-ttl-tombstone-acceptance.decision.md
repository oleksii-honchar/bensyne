---
type: decision
id: DEC-0079
title: "Accept Bensyne DELETED Tombstones (No Purge in TTL Scope)"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, tombstone, bensyne]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "memories/0021-bensyne-forgetfile-tombstone.memory.md"]
---

# DEC-0079: Accept Bensyne DELETED Tombstones (No Purge in TTL Scope)

## Context

`forgetFile` (via `file_service.delete_file`) marks the bensyne `files` row
`DELETED` and persists a tombstone — it does not hard-delete the row. Every
TTL-expired file therefore leaves a tombstone.

## Decision

Accept tombstone accumulation; tombstone purge is out of scope for this
feature. Recorded as a risk (LOW) rather than a new mechanism.

## Rationale

Tombstones are existing forget semantics shared by `handleDelete`, exclude
reconciliation, and manual forgets — TTL just makes them systematic. A purge
would require a bensyne-mcp change (query + batch delete of DELETED rows),
contradicting the "no bensyne changes" boundary the user confirmed, and the
growth is exactly what TTL bounds (1y of files, then tombstoned).

## Consequences

`files` rows accumulate at ~1y-of-ingest per year. If growth becomes observable
(search/list results, DB size), add a bensyne-side tombstone-purge sweep as a
follow-up. The tombstone behavior is made observable by the dedicated TTL e2e,
which asserts the `files` row ends in `status = 'deleted'` with its
`file_chunks` cascade-removed — so the decision stays verifiable, not just
documented.
