---
type: decision
id: DEC-0070
system: bensyne-mcp
title: "Live memory_count for Non-Pooled Banks via Memory Entity Repository"
status: accepted
createdAt: "2026-08-23T20:04:39Z"
updatedAt: "2026-08-23T20:04:39Z"
tags: [memory-bank, list-memory-banks, mcp, mnemosyne, count]
supersedes: []
superseded_by: []
see_also:
  - decisions/0064-unified-list-memory-banks.decision.md
  - decisions/0065-get-stats-banks-scan-phantom-cleanup.decision.md
  - decisions/0071-transient-entity-resolution-router.decision.md
  - decisions/0070-read-only-count-ko-fallback.decision.md
---

# DEC-0070: Live memory_count for Non-Pooled Banks via Memory Entity Repository

## Context

`listMemoryBanks` reported `memory_count: 0, status: registered` for banks not in the live client pool, even when their on-disk `mnemosyne.db` held hundreds of memories (verified live: `tmp-vault` = 0 in list vs 252 via `getMemoryStats`). Root cause: the registry `memory_count` column is dead bookkeeping — never updated in production (no remember/forget path touches it, no event subscribers) — and the DEC-0065 merge falls back to it for non-pooled banks because the pool is lazily populated (only touched banks get clients).

## Decision

In `ListBanksUseCase`, after the existing filesystem ∪ registry ∪ pool merge, fill `memory_count` for **non-active** (non-pooled) entries by resolving the proper memory entity repository via the router — `router.get_stats_for(bank)` — and reading `get_stats().total_memories`. Pooled (`status == "active"`) entries keep live `get_stats().total_memories` (unchanged). Count comes ONLY from `MnemosyneClient.get_stats()` (the memory entity's repository; the library owns the COUNT internally — no raw SQL in bensyne).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Option A — reconcile registry on write | Keeps column in sync | Two mechanisms; column goes stale again unless write-path wiring complete; invasive | More complexity for a display field |
| Option C — document as approximate | Smallest change | Leaves misleading 0 | User asked to fix, not document |
| Raw `SELECT COUNT(*)` helper on `MemoryBankRepository` | Direct | Violates DDD layering (R4: no raw queries); wrong layer — memory counts belong to the memory entity repository | User ruling R4 rejected raw SQL |

## Consequences

- **Positive:** `listMemoryBanks` consistent with `getMemoryStats` regardless of pool state; `tmp-vault` shows 252 without a prior touch; status stays `registered`.
- **Negative:** Registry-only bank counts may change (stored 4 → live count) — behavior change is the point of the fix; tests updated.
- **Neutral:** Registry `memory_count` column stays (dead but harmless); no migration.
