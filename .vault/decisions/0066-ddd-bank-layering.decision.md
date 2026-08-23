---
type: decision
id: DEC-0067
system: bensyne-mcp
title: "DDD Bank Layering Around the Existing MemoryBank Aggregate"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, ddd, aggregate, layering, domain]
supersedes: []
superseded_by: []
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0010-ddd-migration-approach.decision.md
  - decisions/0033-aggregate-repository-service-pattern.decision.md
  - decisions/0003-in-memory-namespace-registry.decision.md
---

# DEC-0067: DDD Bank Layering Around the Existing `MemoryBank` Aggregate

## Context

Codebase inspection (Phase 1): the `MemoryBank` aggregate (`src/domain/memory_bank_aggregate.py`) was production-dead — only self-references, the `InMemoryMemoryBankRepository` test fake, and tests consumed it; DI providers were unreferenced placeholders. Round 2 proposed a raw `Bank` entity + deletion; round 3 (U9) kept the aggregate; round 4 collapsed all components into one service; round 5 (U14) restores proper layering.

## Decision

- The bank stack (DDD layers):
  - **domain**: `MemoryBank` aggregate (existing, kept — O7 vetoed deletion)
  - **infrastructure**: `MemoryBankRepository` (NEW — persistence, `memory_banks.db`) + `MemoryBankRouter` (existing, restored — path authority + instance pool; registry duties removed)
  - **application**: `MemoryBankService` (NEW — business orchestration, sole business API)
  - **interface**: use cases + handlers orchestrate business via `MemoryBankService`, technical wiring via the router (repo convention)
- **The aggregate is KEPT and wired into production**:
  - kept: `MemoryBank` (all existing fields/methods), `MemoryBankSchema`, `MemoryBankActivatedEvent`/`MemoryBankSuspendedEvent`, `InMemoryMemoryBankRepository` (test fake; its contract becomes the repository contract), the aggregate's existing unit tests.
  - one extension: `MemoryBank.update_description(description)` public method.
  - DI `memory_bank_repository` providers repurposed: `InMemoryMemoryBankRepository` placeholder → real `MemoryBankRepository` singleton.
- **Contract (binding for implementation):** the aggregate's `memories` collection is NOT persisted and NOT used in production remember/forget flows (those go through `MnemosyneClient`/mnemosyne.db). The aggregate serves as identity + metadata/lifecycle entity; `memory_count` is denormalized bookkeeping. Routing mnemosyne writes through `aggregate.remember()` is FORBIDDEN (second source of truth).
- **Deleted:** `MemoryBankRegistry` (`registry.py` — in-memory descriptions; superseded by the repository), old `mnemosyne/bank_manager.py` (path rules moved into the router). `MemoryBankManagerService` is never created (U13).
- The round-2 raw `Bank` entity, `BankSchema`, `bank_events.py`, `BankRepository`, and the `MemoryBankInfo`/`memory_events.py` deletion plan are all withdrawn.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Raw `Bank` entity + delete aggregate (round 2) | Lean | Two competing concepts; discards existing domain surface; user veto | U9 |
| Single service with everything (round 4) | One component | Mixed layers; service too large | U14 |
| Keep aggregate aspirational, persist a parallel structure | Zero risk | Persistence and domain entity diverge — DDD violation | U9 |
| Extend aggregate with persistence-aware methods | Cohesive | Mixes infra concerns into domain | Repository owns persistence; aggregate stays pure |

## Consequences

- **Positive:** One unambiguous bank concept; ubiquitous language consistent across layers and MCP tools. Proper DDD layering: domain ↔ infrastructure ↔ application ↔ interface. Existing domain tests + fake contract reused; router pool logic untouched; no dead code introduced (the aggregate becomes live). `activate`/`suspend`/`remember`/`forget` semantics available for future tools without schema changes.
- **Negative:** `memories` collection and `remember`/`forget` remain unused in production — risk of future misuse; mitigated by the explicit binding contract above (spec §4.1).
