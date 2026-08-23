---
type: concept
system: bensyne-mcp
title: "MemoryBank Aggregate"
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [domain, aggregate, memory-bank]
see_also:
  - concepts/0002-memory-domain.concept.md
  - decisions/0011-result-pattern-error-handling.decision.md
  - specifications/0001-bensyne-ddd-migration.spec.md
  - decisions/0062-persistent-bank-registry.decision.md
  - decisions/0066-ddd-bank-layering.decision.md
---

# Concept: MemoryBank Aggregate

## What

MemoryBank is the domain aggregate root for memory banks in bensyne. It serves as the **identity + metadata/lifecycle entity** for a bank: name, description, status, timestamps, and denormalized memory count. It is the single bank concept across the codebase and MCP tools (ubiquitous language).

## Production Status

**LIVE as of 2026-08-23** (bank layout normalization round 5). The aggregate was previously production-dead (only self-references + the `InMemoryMemoryBankRepository` test fake consumed it); it is now wired into production via `MemoryBankRepository` → `memory_banks.db`.

## Why

The aggregate enforces domain invariants (non-empty description, schema-validated name) and produces domain events returned in `Result.events` — not stored as properties. Round-5 wiring persists it as the durable bank registry (replacing the in-memory `MemoryBankRegistry`).

## Key Details

- **Location:** `src/domain/memory_bank_aggregate.py`
- **Entity fields:** `name`, `description`, `status`, `created_at`, `last_accessed`, `memory_count`, `memories`
- **Factory:** `of()` — Result-returning, non-empty description invariant; `MemoryBankSchema` (`[a-zA-Z0-9_]+` name)
- **Extension (2026-08-23):** `update_description(description)` — frozen update, schema-validated, Result-returning
- **Persistence:** `MemoryBankRepository` (`src/infrastructure/bank/memory_bank_repository.py`) — SQLAlchemy + WAL + `ON CONFLICT(name) DO UPDATE`, `memory_banks.db` at data root. Contract matches the existing `InMemoryMemoryBankRepository` fake.
- **Application service:** `MemoryBankService` (`src/application/services/memory_bank_service.py`) — business orchestration (register/get/list/ensure_default_bank), no paths, no pool.
- **Operations (available for future tools, currently unused in production):**
  - `remember(memory)` — adds memory; rejects if bank not active; produces MemoryRememberedEvent
  - `forget(memory_id)` — removes memory; rejects if not found; produces MemoryForgottenEvent
  - `activate()` / `suspend()` — lifecycle; produce MemoryBankActivatedEvent / MemoryBankSuspendedEvent
- **Events:** MemoryRememberedEvent, MemoryForgottenEvent, MemoryBankActivatedEvent, MemoryBankSuspendedEvent — all returned in `Result.events`

## Binding Misuse Contract

- The aggregate's `memories` collection is **NOT persisted** (mnemosyne.db owns memories) and **NOT used** in production remember/forget flows — those go through `MnemosyneClient`/mnemosyne.db.
- Routing mnemosyne writes through `aggregate.remember()` is **FORBIDDEN** (would create a second source of truth).
- `memory_count` is **denormalized bookkeeping**, not a live count of mnemosyne memories.
