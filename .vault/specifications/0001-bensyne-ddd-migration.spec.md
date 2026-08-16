---
type: specification
kind: migration
system: bensyne-mcp
title: "bensyne DDD Migration"
status: completed
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
owner: ""
target: null
see_also:
  - decisions/0010-ddd-migration-approach.decision.md
  - decisions/0011-result-pattern-error-handling.decision.md
  - concepts/0002-memory-domain.concept.md
  - concepts/0003-memory-bank-aggregate.concept.md
  - architectures/bensyne-mcp/containers/0001-container.container.md
---

# Specification: bensyne DDD Migration

## Goal

Migrate bensyne from flat Python architecture to hexagonal DDD with Result pattern, rich domain objects, use cases, and repository abstraction. 1352 tests collected, domain coverage high.

## Architecture

Hexagonal architecture with 4 layers:
- **Adapters:** FastMCP Server, health endpoints, HTTP controllers
- **Application:** Use cases (RememberMemory, RecallMemory, ForgetMemory, UpdateMemory, Sleep, ListBanks, RegisterBank, SearchFiles, ExpandFileRelations, FetchFile), services (HashIndexService, FileService)
- **Domain:** Entities (Memory, MemoryBank, File, FileChunk, FileRelation), value objects (FileHash), aggregates (MemoryBankAggregate, FileMetadataAggregate), events (MemoryRemembered, MemoryForgotten, MemoryBankActivated, MemoryBankSuspended, file events), Result pattern
- **Infrastructure:** MnemosyneClient, HashIndexService, FileMetadataConnectionManager, ConfigurationService, DI container, structured logging

## Phases Completed

1. **Foundation** — Result pattern, Pydantic validation, domain events, structured logging
2. **Domain Layer** — Memory entity, MemoryBank entity, FileHash value object, MemoryBankAggregate, Pydantic schemas, domain events
3. **Application Layer** — BaseUseCase, 7 use cases, hash index service
4. **Infrastructure** — MnemosyneClient wrapper, HashIndexService, ConfigurationService, DI container
5. **Integration** — MCP tool handlers adapted to use cases, MemoryBankRouter refactored, E2E tests

## Risks

- ⚠️ ADR-006 (Prisma ORM) — external reference (pre-vault, no in-vault referent) — proposed but not implemented — SQLAlchemy used instead (per implementation plan)
- Future: Replace in-memory repositories with database-backed implementations
- Future: Feature flags for gradual production rollout

## Test Results

| Metric | Value |
|--------|-------|
| Tests | 1352 collected |
| Coverage | 92.22% ⚠️ unverified this session |
| Domain coverage | 100% |
