---
type: decision
id: DEC-0083
system: racochu
title: "Recovery Is Additive; Changed Files Use Existing Change Semantics"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, additive, change-semantics, stale-chunks]
supersedes: []
superseded_by: []
see_also:
  - decisions/0036-forget-after-ingest-on-file-update.decision.md
  - decisions/0084-recover-hash-gate-chunk-set-check.decision.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0083: Recovery Is Additive; Changed Files Use Existing Change Semantics

## Context

Recover must re-ingest missing chunks. Two semantics exist: additive (submit only missing, keep
existing) vs change (forget stale + re-ingest). Stale-chunk cleanup requires destructive forget
calls; user scope asks only for missing-chunk recovery.

## Decision

- Present, unchanged file (`fileHash` equal): submit **only missing chunk indexes** via
  `IngestChunkUseCase` (enrichment per config, then `trackMemory`).
- Changed file (`fileHash` differs) or file absent on bensyne: full re-ingest via
  `ProcessFileUseCase` (`change`/`add`) — existing change semantics (forget stale + ingest).
- Never call forget during recover for stale-chunk cleanup; stale chunks are out of scope for v1.

## Alternatives Considered

- Pure additive even for changed files — rejected: leaves stale memories pointing at old content.
- Stale-chunk cleanup in v1 — deferred (destructive, out of scope).

## Consequences

- Recover is non-destructive by default; only the changed-file path performs forgets (as normal
  change processing already does).
- Open decisions OD-1/OD-2 (stale reconciliation, additive-vs-change) resolved as stated.
