---
type: decision
id: DEC-0033
system: racochu
title: "Aggregate-Repository-Service Pattern"
status: accepted
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-08-01T12:00:00Z"
tags: [architecture, ddd]
see_also: [concepts/0014-file-memory-tracking.concept.md]
---

# DEC-0033: Aggregate-Repository-Service Pattern

## Context
Need to define the proper DDD structure for file→memory tracking.

## Decision
Use aggregate root pattern with repository for persistence and service for business logic:
- `FileMemoryTracker` aggregate with domain behavior
- `FileMemoryTrackerRepository` for data access
- `FileMemoryTrackerService` for orchestration

## Rationale
1. **Encapsulation** — Aggregate controls its own state
2. **Separation of concerns** — Repository handles persistence, service handles orchestration
3. **Testability** — Each layer can be tested independently
4. **DDD alignment** — Follows hexagonal architecture principles

## Alternatives Considered
1. **Interface-based** — Empty interface with service implementation — less clear
2. **Direct repository** — Service directly uses repository — mixes concerns
3. **Single class** — All logic in one class — harder to maintain

## Consequences
- **Positive**: Clean separation, easier testing, better maintainability
- **Negative**: More classes to maintain
- **Mitigation**: Well-defined responsibilities per layer
