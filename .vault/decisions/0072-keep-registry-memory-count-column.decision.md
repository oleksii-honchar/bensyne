---
type: decision
id: DEC-0073
system: bensyne-mcp
title: "Keep Registry memory_count Column — No Event Wiring, No Migration"
status: accepted
createdAt: "2026-08-23T20:04:39Z"
updatedAt: "2026-08-23T20:04:39Z"
tags: [memory-bank, registry, schema, events, deferred]
supersedes: []
superseded_by: []
see_also:
  - decisions/0069-live-memory-count-non-pooled-banks.decision.md
  - decisions/0062-persistent-bank-registry.decision.md
---

# DEC-0073: Keep Registry memory_count Column — No Event Wiring

## Context

The `MemoryBank` aggregate has `increment_memory_count`/`decrement_memory_count` + `MemoryRememberedEvent`/`MemoryForgottenEvent`, but no production caller (tests only). The registry `memory_count` column is dead bookkeeping: always 0 unless manually set. With the live-count fix (DEC-0070), the column is no longer the display source for non-pooled banks.

## Decision

Do NOT wire remember/forget → counter → save. Live `get_stats()` is the single source of truth for `memory_count` in listings. The registry `memory_count` column is left as-is (dead bookkeeping, harmless). Column removal deferred — it's still read by registry consumers/tests; removal is optional churn.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Wire remember/forget → increment + save | Defense-in-depth | Write-path complexity for a display field; two mechanisms to keep in sync | Over-engineering for a read-side fix |
| Drop the column | Cleaner schema | Migration + test churn for a harmless dead field | Premature optimization |

## Consequences

- **Positive:** Simpler; the dead column remains but is no longer the display source.
- **Neutral:** If the column causes confusion later, a follow-up can drop it.
