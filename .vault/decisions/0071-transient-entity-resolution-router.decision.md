---
type: decision
id: DEC-0072
system: bensyne-mcp
title: "Transient Entity Resolution on Router — get_stats_for, Never Pooled"
status: accepted
createdAt: "2026-08-23T20:04:39Z"
updatedAt: "2026-08-23T20:04:39Z"
tags: [memory-bank, router, entity-resolution, transient, pool, architecture]
supersedes: []
superseded_by: []
see_also:
  - decisions/0069-live-memory-count-non-pooled-banks.decision.md
  - decisions/0063-layered-bank-components.decision.md
  - decisions/0064-unified-list-memory-banks.decision.md
---

# DEC-0072: Transient Entity Resolution on Router — get_stats_for

## Context

The pool (`router.instances`) is lazy by design; `get_instance()` both resolves AND pools a bank. Using it for a listing would mutate pool state → status flips to `active` on the next list and LRU churns. The fix must not depend on pool state (the observed defect was pool-state-dependent).

## Decision

Add `MemoryBankRouter.get_stats_for(memory_bank) -> Result[dict]`: resolve the `MnemosyneClient` for the requested bank (mirroring `get_instance()`'s resolution — R6), but do NOT add it to `self.instances`. Guard: only construct when `get_mnemosyne_db_path().exists()` (no dir/db creation). Delegates to `client.get_stats()`. The router remains the path + entity resolution authority (DEC-0064/U14, established in 0063-layered-bank-components).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Reuse `router.get_instance(bank)` | Simpler, existing method | Pools the bank → status becomes `active`, LRU churn, defeats DEC-0065 precedence | Mutates pool state on read |
| `MemoryBankService.count_memories(bank)` | Service-level abstraction | Service would need router access and operate on raw paths/entities it doesn't own | Violates R5 (entity-only service) |
| Raw sqlite COUNT helper | Direct | Violates R4 (no raw queries) | Wrong layer |

## Consequences

- **Positive:** Listing is read-only: no pool mutation, no status flips, no dir/db creation. Router stays as entity resolution authority.
- **Negative:** Each `listMemoryBanks` call constructs one transient client per non-active bank (trivial at 5 banks; cache later if needed).
