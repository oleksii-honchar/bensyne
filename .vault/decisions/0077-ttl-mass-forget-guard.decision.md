---
type: decision
id: DEC-0078
title: "Reuse Mass-Forget Guard (MASS_FORGET_THRESHOLD=20 + RACOCHU_RECONCILE_FORCE_FORGET=1)"
status: accepted
createdAt: "2026-08-25T13:45:19Z"
updatedAt: "2026-08-25T13:45:19Z"
system: racochu
tags: [ttl, retention, safety, guard]
see_also: ["specifications/0006-source-ttl-sweep.spec.md", "decisions/0073-ttl-sweep-racochu-side.decision.md"]
---

# DEC-0078: Reuse Mass-Forget Guard (MASS_FORGET_THRESHOLD=20 + RACOCHU_RECONCILE_FORCE_FORGET=1)

## Context

A first TTL backfill sweep (after 1y of accumulation) could exceed 20 files per
source. The exclude reconciliation already has a guard against catastrophic
mass-forget.

## Decision

`TtlReconciliationService` uses the same threshold and env override, extracted
to a shared `mass-forget-guard.ts` (values unchanged).

## Rationale

One consistent safety knob; TTL is age-bounded but not immune to
misconfiguration (e.g. `ttlDays: 1` on a huge source).

## Consequences

Operator must run the initial backfill with
`RACOCHU_RECONCILE_FORCE_FORGET=1` — documented in spec §6 and in the guard's
log message.
