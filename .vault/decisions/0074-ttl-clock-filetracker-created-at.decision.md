---
type: decision
id: DEC-0075
title: "TTL Clock Is FileTracker.createdAt (First Ingest), Not updatedAt"
status: superseded
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-10-28T18:22:10Z"
system: racochu
tags: [ttl, retention, filetracker]
superseded_by: ["DEC-0118"]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md", "decisions/0118-ttl-activity-clock-gate.decision.md"]
deprecated:
  date: 2026-10-28
  reason: "TTL eligibility re-based on the derived activity clock; createdAt demotes to audit-only."
  superseded_by: DEC-0118
---

# DEC-0075: TTL Clock Is FileTracker.createdAt (First Ingest), Not updatedAt

> **Superseded by DEC-0118 (2026-10-28):** the createdAt clock and its
> `findExpiredBySourceId` SQL age predicate are replaced by the stateless activity-clock gate;
> see [[0118-ttl-activity-clock-gate]]. The "If a source needs touch-reset semantics later"
> consequence below is what happened — body kept unchanged as the audit trail.

## Context

Re-ingesting a changed file bumps `FileTracker.updatedAt` (upsert `update`
clause). Basing TTL on `updatedAt` would keep any actively re-ingested file
alive indefinitely, contradicting "1y then delete old records".

## Decision

Age filter uses `createdAt < now - ttlDays`, applied in SQL by a new repository
query (`findExpiredBySourceId`). The `FileMemoryTracker` aggregate stays
timestamp-free (pure value object).

## Consequences

A file first ingested 13 months ago is forgotten even if re-ingested last week.
Accepted for agent-sessions (per-day, mostly immutable). If a source needs
touch-reset semantics later, switch to `updatedAt` in the same query — no schema
change.
