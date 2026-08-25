---
type: decision
id: DEC-0075
title: "TTL Clock Is FileTracker.createdAt (First Ingest), Not updatedAt"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, filetracker]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md"]
---

# DEC-0075: TTL Clock Is FileTracker.createdAt (First Ingest), Not updatedAt

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
