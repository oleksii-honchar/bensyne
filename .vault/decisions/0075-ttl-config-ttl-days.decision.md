---
type: decision
id: DEC-0076
title: "Config Shape Is watchSources[].ttlDays (Optional Positive Int)"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-10-28T18:22:10Z"
system: racochu
tags: [ttl, retention, config, zod]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0025-configuration-management.decision.md", "decisions/0118-ttl-activity-clock-gate.decision.md"]
---

# DEC-0076: Config Shape Is watchSources[].ttlDays (Optional Positive Int)

## Context

Need a TTL parameter per source, zod-validated, hot-reload friendly.

## Decision

`ttlDays?: number` (`z.number().int().positive().optional()`) in
`watchSourceConfigSchema`. Absent ⇒ no sweep for that source. No default in
`DEFAULT_CONFIG_SEED` (opt-in).

## Alternatives Considered

ISO-8601 duration (`P1Y`) or `"1y"` strings — rejected: adds a duration parser
for no benefit; `365` days is the requirement.

## Consequences

1y == 365 days (no leap-year nuance — fine for retention). Config changes
hot-reload and apply on the next sweep run.

## Semantics Update (2026-10-28, per DEC-0118)

`ttlDays` now measures **days since last activity** (file mtime; row
`updatedAt ?? createdAt` only for absent files) instead of days since first
ingest. Same key, same validators, no config migration; opt-in scope is now
also the feature-boundary control (unconfigured sources — e.g. permanent
materials like the obsidian bank — are intentionally never swept, by owner
decision). Present-day channel note: the sweep's absent-file fallback uses
row `createdAt` only until a `updatedAt` read channel exists (the shared
helper already pins the full precedence).

See [[0118-ttl-activity-clock-gate]].
