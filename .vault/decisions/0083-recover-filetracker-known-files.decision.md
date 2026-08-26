---
type: decision
id: DEC-0084
system: racochu
title: "FileTracker Rows Are the Known-Files Source; No Local Schema Change in v1"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, file-tracker, known-files, repository]
supersedes: []
superseded_by: []
see_also:
  - decisions/0028-file-memory-tracking-prisma-sqlite.decision.md
  - decisions/0041-filetracker-schema-extension.decision.md
  - decisions/0084-recover-hash-gate-chunk-set-check.decision.md
  - concepts/0014-file-memory-tracking.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0084: FileTracker Rows Are the Known-Files Source; No Local Schema Change in v1

## Context

"Process only files already known to the local database" — `FileTracker` (filePath unique,
sourceId, memoryBank, fileHash) is that registry. It stores no chunk-level identity. Verifying
chunk completeness requires either an MCP-side read (DEC-0080) or a local chunk registry.

## Decision

Iterate `FileTracker` rows (optionally filtered by sourceId). No Prisma schema change in v1 —
the expected chunk set is computed locally at verify time (chunking without enrichment is
CPU-only). Files with a tracker row but no file on disk are skipped with a warning
(non-destructive).

**Verified gap → new query:** `FileTrackerRepository` had NO listing query; the existing
`FileMemoryTrackerRepository.findBySourceId` returns hash-less aggregates. Added
`FileTrackerRepository.findTrackedBySourceId(sourceId?)` returning full `FileTracker` aggregates
(incl. `fileHash`/`hardwareId`), skipping malformed rows — required for the DEC-0085 change gate.

## Alternatives Considered

- Add chunk-count/hash fingerprint to `FileTracker` at ingest — deferred (OD-3): schema
  migration + backfill + write-path change; only saves CPU re-chunking on future passes.

## Consequences

- Each recover pass re-chunks every tracked file locally (CPU). Bounded by file count/size;
  acceptable for a maintenance mode.
