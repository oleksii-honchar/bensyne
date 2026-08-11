---
type: concept
title: "MemoryBank Aggregate"
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [domain, aggregate, memory-bank]
see_also:
  - "concepts/0002-memory-domain.concept.md"
  - "adrs/0008-result-pattern-error-handling.adr.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
---

# Concept: MemoryBank Aggregate

## What

MemoryBankAggregate is the aggregate root in bensyne's domain model, orchestrating MemoryBank and Memory entities with domain invariants and event production. It is the only boundary through which memories can be added or removed.

## Why

The aggregate enforces critical invariants: a bank must be active to remember (accept memories), and a memory cannot be removed if it doesn't exist. Domain events are produced by aggregate operations and returned in `Result.events` — not stored as properties on the aggregate.

## Key Details

- **Location:** `src/domain/aggregates/memory_bank_aggregate.py`
- **Composition:** Contains `MemoryBank` entity + `List[Memory]` entities
- **Operations:**
  - `remember(memory)` — adds memory; rejects if bank not active; produces MemoryCreatedEvent
  - `forget(memory_id)` — removes memory; rejects if not found; produces MemoryDeletedEvent
  - `activate()` — activates bank; produces MemoryBankActivatedEvent
  - `suspend()` — suspends bank; produces MemoryBankSuspendedEvent
- **Invariants:** Bank must be active to remember; memory must exist to forget; all operations return `Result` with optional domain events
- **Events:** MemoryCreatedEvent, MemoryDeletedEvent, MemoryBankActivatedEvent, MemoryBankSuspendedEvent — all returned in `Result.events`
