---
type: decision
id: DEC-0074
title: "TTL Sweep Executes on Racochu Side, Deletion via Bensyne MCP forgetFile"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, racochu, bensyne]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "architectures/racochu/components/0001-server-components.component.md"]
---

# DEC-0074: TTL Sweep Executes on Racochu Side, Deletion via Bensyne MCP forgetFile

## Context

Sources (e.g. `agent-sessions` under `~/.agent-sessions`) accumulate
files forever; a `ttl` should delete files and their mnemosyne memories after a
retention period. The user's direction said deletion should be "executed on the
bensyne MCP side" and later confirmed "racochu delete on ttl".

## Decision

The sweep (scheduling, age decision, tracker cleanup) lives in racochu as
`TtlReconciliationService`. Deletion **executes through the bensyne MCP
`forgetFile` tool** (`BensyneClient.forgetByFile`) — so execution IS on the
bensyne side, with its shared-memory guard. Bensyne-mcp (Python) is unchanged.

## Alternatives Considered

- Bensyne-internal asyncio task sweeping `files` by `source_type` + `created_at`
  — rejected: TTL granularity lost (only `source_type` survives the wire),
  config duplication, stale racochu trackers, resurrection risk.
- Per-file `expires_at` propagated at ingest — rejected: schema migration +
  contract change + same stale-tracker problem; over-engineered.

## Consequences

Daily sweep depends on racochu being run at least once per interval (startup
sweep covers missed days; optional OS cron `racochu --ttl-sweep` is the ops
fallback). Single source of truth, idempotent, reuses existing patterns.
