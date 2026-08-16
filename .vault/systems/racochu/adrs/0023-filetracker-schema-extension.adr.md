---
type: adr
id: ADR-0028
title: "Add fileHash and hardwareId Fields to FileTracker Schema"
status: accepted
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [schema, filetracker, file-hash, hardware-id]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0021-file-hash-deduplication-metadata.adr.md"
  - "adrs/0022-native-machine-id-hardware-detection.adr.md"
  - "concepts/0007-file-memory-tracking.concept.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0028: Add fileHash and hardwareId Fields to FileTracker Schema

## Context

File hash and hardware ID need to be stored per-file for local deduplication checks and audit trail of device ingestion. Current FileTracker schema doesn't support these fields.

## Decision

Add `fileHash` (nullable `String`) and `hardwareId` (nullable `String`) to FileTracker schema with Prisma indexes. Repository method `updateFileTrackerHash` uses Prisma `updateMany` to persist on the FileTracker parent record after upsert.

## Alternatives Considered

1. **FileMemoryTracker instead** — wrong level; would duplicate data across memory entries (one-to-many mismatch)
2. **Separate FileHardwareId table** — over-engineering
3. **No tracking** — user explicitly requested this

## Consequences

- **Positive:** Simple audit trail of device ingestion per file
- **Negative:** Schema migration required
- **Mitigation:** Nullable fields; existing entries unaffected; `updateFileTrackerHash` called only after upsert
