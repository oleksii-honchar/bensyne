---
type: decision
id: DEC-0065
system: bensyne-mcp
title: "Unified listMemoryBanks — Filesystem ∪ Pool ∪ Registry"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, list-memory-banks, mcp, filesystem, pool]
supersedes: []
superseded_by: []
see_also:
  - decisions/0001-namespace-registration-protocol.decision.md
  - concepts/0003-memory-bank-aggregate.concept.md
---

# DEC-0065: Unified `listMemoryBanks` — Filesystem ∪ Pool ∪ Registry

## Context

Three mechanisms each answered "which banks exist?": filesystem dirs (5 in the live run), router instance pool (2), in-memory registry. `listMemoryBanks` merged pool + registry only; `getMemoryStats.banks` used a different (library) scan — the 2-vs-5 mismatch.

## Decision

Canonical truths: **filesystem = existence**, **pool = liveness**, **memory_banks.db = descriptions/lifecycle**. `ListBanksUseCase(memory_bank_service, router, logger)` emits one entry per bank from the union of `router.list_bank_dirs()` + `router.instances` (pool) + `memory_bank_service.list_memory_banks()`; status precedence `active` (pool) > stored status (`registered`/`suspended`) > `on_disk`; description from memory_banks.db (empty string when absent). `getMemoryStats.banks` uses the same filesystem scan (DEC-0066). Entry shape UNCHANGED (verified `list_banks_use_case.py:49-71`): `{name, bank, description, memory_count, status}` — `name` == `bank` (both the bank name), `memory_count` = live stats when active, stored value otherwise.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Pool-only listing (today) | Simple | Banks invisible until touched; restart-sensitive | The observed defect |
| Registry-only listing | Stable across restarts | Registry can lag filesystem | Existence comes from where data physically lives |
| Single-service listing (round 4) | One dependency | Pool lived in the service (U14 moved it back to the router) | Router restored as infra |

## Consequences

- **Positive:** `listMemoryBanks` = stable, complete, restart-independent; agent bank-awareness (U2). 2-vs-5 class of bugs eliminated.
- **Negative:** Use case depends on service + router — both are stable, injected components. Response includes banks the process never touched — additive, consumers verified compatible.
