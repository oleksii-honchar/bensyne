---
type: decision
id: DEC-0077
title: "TTL Sweep Cadence: Startup (All Modes) + Daily Interval (Watch Mode) + --ttl-sweep CLI"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, scheduler, cli]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md"]
---

# DEC-0077: TTL Sweep Cadence: Startup (All Modes) + Daily Interval (Watch Mode) + --ttl-sweep CLI

## Context

"Check once a day, like garbage collection." No scheduler exists in either app;
no cron infra.

## Decision

Startup sweep in all modes (guarded, non-fatal, mirrors exclude
reconciliation); `setInterval(24h).unref()` in watch mode;
`--ttl-sweep` for manual/CI runs (honors `-s/--source` and `--dry-run`).

## Alternatives Considered

`@nestjs/schedule` cron (new dependency — rejected); OS cron (viable,
documented as ops option, not required).

## Consequences

Missed days self-heal at next startup; the destructive sweep is also invocable
on demand. The daily sweep must not race in-flight ingests: it awaits
`FileProcessingQueue.waitForEmpty()` and re-checks each tracker's expiry
immediately before `forgetByFile`.
