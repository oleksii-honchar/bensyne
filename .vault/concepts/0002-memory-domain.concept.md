---
type: concept
title: "Memory Domain Model"
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [domain, memory, entity]
see_also:
  - "concepts/0003-memory-bank-aggregate.concept.md"
  - "adrs/0007-ddd-migration-approach.adr.md"
  - "adrs/0008-result-pattern-error-handling.adr.md"
---

# Concept: Memory Domain Model

## What

The Memory entity is the core domain object in bensyne, representing a durable memory stored within a MemoryBank. Each memory has content, importance, source, and scope — and is validated through Pydantic schemas before creation.

## Why

Memory is the primary thing bensyne manages. The domain model enforces invariants: content must be non-empty, importance must be between 0.0 and 1.0, scope must be one of `working`, `episodic`, `semantic`, or `suspended`. Factory method `Memory.of(properties)` validates through `MemorySchema` and returns `Result[Memory]`.

## Key Details

- **Location:** `src/domain/entities/memory.py`
- **Validation:** Pydantic `MemorySchema` in `src/domain/schemas/memory_schema.py`
- **Operations:** `of(properties)` — create with validation; `update(content, importance)` — update with new instance; `suspend()` — transition to suspended scope
- **Invariants:** Frozen dataclass (immutable); update produces new instance; suspend rejects already-suspended memories
- **Events:** MemoryCreatedEvent, MemoryDeletedEvent produced by MemoryBankAggregate operations (not by the entity directly)
