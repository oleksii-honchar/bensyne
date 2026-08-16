---
type: concept
system: bensyne-mcp
title: "Memory Domain Model"
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [domain, memory, entity]
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0010-ddd-migration-approach.decision.md
  - decisions/0011-result-pattern-error-handling.decision.md
---

# Concept: Memory Domain Model

## What

The Memory entity is the core domain object in bensyne, representing a durable memory stored within a MemoryBank. Each memory has content, importance, source, and scope — and is validated through Pydantic schemas before creation.

## Why

Memory is the primary thing bensyne manages. The domain model enforces invariants: content must be non-empty, importance must be between 0.0 and 1.0, scope must be one of `working`, `episodic`, `semantic`, or `suspended`. Factory method `Memory.of(properties)` validates through `MemorySchema` and returns `Result[Memory]`.

## Key Details

- **Location:** `src/domain/memory_entity.py`
- **Validation:** Pydantic `MemorySchema` in `src/domain/schemas/memory_schema.py`
- **Operations:** `of(properties)` — create with validation; `update(content, importance)` — update with new instance; `suspend()` — transition to suspended scope
- **Invariants:** Frozen dataclass (immutable); update produces new instance; suspend rejects already-suspended memories
- **Events:** MemoryRememberedEvent, MemoryForgottenEvent produced by MemoryBankAggregate operations (not by the entity directly)
