---
type: decision
id: DEC-0012
system: bensyne-mcp
title: "Pydantic for Data Validation"
status: accepted
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [validation, pydantic, domain]
supersedes: []
superseded_by: []
see_also:
  - decisions/0011-result-pattern-error-handling.decision.md
  - concepts/0002-memory-domain.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0012: Pydantic for Data Validation

## Context

The DDD migration required a validation framework to replace basic type hints and manual validation. Domain entities need factory methods (`Memory.of`, `MemoryBank.of`) that validate input through Pydantic schemas before creating domain objects.

## Decision

**Use Pydantic for data validation and serialization.** Pydantic schemas are defined in `src/domain/schemas/` and used by domain entity factory methods. API request/response models also use Pydantic.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Pydantic (chosen)** | Strong typing, runtime validation, schema validation, serialization, ecosystem support | Additional dependency, learning curve | — |
| **Marshmallow** | Mature, flexible | More verbose, less type-safe | Pydantic provides better type safety |
| **Cerberus** | Simple, lightweight | Limited validation features | Pydantic more comprehensive |

## Consequences

- **Positive:** Strong runtime validation, automatic serialization, better error messages, type hints integration
- **Negative:** Additional dependency, learning curve for team
- **Neutral:** Pydantic schemas in `src/domain/schemas/` serve as both validation and documentation
