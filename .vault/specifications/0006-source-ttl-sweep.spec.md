---
type: specification
kind: feature
status: completed
title: "Source TTL Sweep (Racochu)"
owner: ""
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, racochu, feature]
see_also: ["decisions/0073-ttl-sweep-racochu-side.decision.md", "decisions/0074-ttl-clock-filetracker-created-at.decision.md", "decisions/0075-ttl-config-ttl-days.decision.md", "decisions/0076-ttl-sweep-cadence.decision.md", "decisions/0077-ttl-mass-forget-guard.decision.md", "decisions/0078-ttl-tombstone-acceptance.decision.md"]
---

# Specification: Source TTL Sweep (Racochu)

## Goal

Add an optional per-source time-to-live (`ttlDays`) to racochu's watch-source
configuration. Once a source's retention period elapses, the files tracked for
that source and their mnemosyne memories are forgotten — once a day, like
garbage collection. The sweep runs on the racochu side (config + decision +
both-DB cleanup) and executes deletion through the bensyne MCP `forgetFile`
tool (shared-memory guard applies). No changes to bensyne-mcp (Python), no
Prisma schema change. Scope: only sources with `ttlDays` set are swept;
vault/obsidian sources unaffected unless configured; default-bank non-file
memories are out of scope.

## Key Design

- **Config:** `watchSources[].ttlDays?: number`
  (`z.number().int().positive().optional()`) in `watchSourceConfigSchema`.
  Absent ⇒ no sweep for that source. Hot-reload friendly.
- **Clock:** `FileTracker.createdAt` (first ingest) — age filter in SQL via
  `findExpiredBySourceId(sourceId, cutoff)`; no migration (Prisma already
  persists `createdAt`).
- **Service:** `TtlReconciliationService` (`run(dryRun?, sourceId?)`,
  `startDailySweep()` = `setInterval(24h).unref()`,
  `stop()`/`onApplicationShutdown`). Non-fatal, idempotent, never throws;
  mirrors `ExcludeReconciliationService`.
- **Coordination:** daily sweep awaits `FileProcessingQueue.waitForEmpty()`;
  re-checks each tracker's `createdAt < cutoff` immediately before
  `forgetByFile`.
- **Guard:** shared `mass-forget-guard.ts` — `MASS_FORGET_THRESHOLD=20` +
  `RACOCHU_RECONCILE_FORCE_FORGET=1`; `expired` counted before guard;
  `refusedMassForget` reported.
- **Deletion:** per expired tracker `forgetByFile(filePath, memoryBank)` → on ok
  `deleteByFilePath(filePath)`; failures logged, non-fatal.
- **CLI/wiring:** `--ttl-sweep` (honors `-s/--source` + `--dry-run`); startup
  sweep in all modes before `--force-reprocess`/`--resume` dispatch; watch mode
  starts the daily interval.
- **Tombstones:** `forgetFile` marks bensyne `files` row `DELETED` (tombstone,
  chunks cascade) — accepted, out of scope for purge (see DEC-0079).

## Implementation Status

Implemented and verified per session implementation plan (all tasks complete):

- Task 1 config schema ✓ · Task 2 repo/service query ✓ · Task 3 guard
  extraction ✓ · Task 4 TtlReconciliationService ✓ · Task 5 CLI + main.ts
  wiring ✓ · Task 6 TTL e2e suite (3/3 pass; full-suite-green blocked by
  pre-existing bensyne-mcp `forgetMemory` image issue, not a TTL regression) ✓ ·
  Task 7 docs + `ttlDays: 365` config (agent-sessions + dev.yaml) ✓
- Config set in `~/.config/racochu.yaml` (agent-sessions) and
  `apps/racochu/dev.yaml` (tmp-agent-sessions): `ttlDays: 365`.

## Risks

- First backfill sweep >20 files/source → guard refuses; run once with
  `RACOCHU_RECONCILE_FORCE_FORGET=1` (documented).
- Sweep/ingest race → `waitForEmpty()` + per-file expiry re-check.
- `files` DELETED tombstones accumulate (~1y-of-ingest per year) → accepted,
  revisit only if growth observable.
- TTL clock forgets actively re-ingested files → accepted per user decision
  (agent-sessions per-day, mostly immutable).
