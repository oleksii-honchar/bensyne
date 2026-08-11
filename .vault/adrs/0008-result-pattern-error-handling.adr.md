---
type: adr
id: ADR-0008
title: "Result Pattern for Error Handling"
status: accepted
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [result, error-handling, domain, pattern]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0007-ddd-migration-approach.adr.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0008: Result Pattern for Error Handling

## Context

The original bensyne architecture used exception-based error handling, making errors implicit and harder to test. Domain operations returned raw values or threw exceptions, requiring try/catch blocks throughout the codebase. This made it difficult to reason about error paths and to test domain logic in isolation.

The DDD migration required an explicit error handling strategy that integrates with domain events — allowing aggregate operations to produce both a value and domain events on success, or errors on failure.

## Decision

**Implement Result pattern for explicit error handling.** A generic `Result[T]` type wraps all domain operations, returning either a successful value (with optional domain events) or a list of errors. Domain events are returned alongside values in `Result.events`, not stored as properties of entities or aggregates — following the racochu pattern.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Result pattern (chosen)** | Explicit errors in signatures, testability, functional composition, domain event support | More verbose code, learning curve for team | — |
| **Exception-based** | Simple, familiar | Implicit errors, hard to test, try/catch overhead, no event support | Not suitable for DDD domain layer |
| **Optional pattern** | Simple, type-safe | Limited error information, no event support | Result pattern more comprehensive |

## Consequences

- **Positive:** Explicit error handling, better testability, functional composition, type-safe error handling, domain events returned with results
- **Negative:** More verbose code, learning curve for team, requires careful implementation
- **Neutral:** Replaces exception-based handling across all layers; all 23 use cases and domain operations now return Result
