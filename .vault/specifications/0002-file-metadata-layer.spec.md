---
type: specification
kind: feature
title: "File Metadata and Relation Storage Layer"
status: completed
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
owner: ""
target: null
see_also:
  - "adrs/0010-sqlite-file-metadata-storage.adr.md"
  - "adrs/0011-standalone-file-entities.adr.md"
  - "adrs/0012-file-specific-mcp-tools.adr.md"
  - "adrs/0013-racochu-source-enrichment.adr.md"
  - "adrs/0014-file-content-reconstruction.adr.md"
  - "concepts/0004-file-metadata-aggregate.concept.md"
  - "concepts/0007-file-metadata-layer.concept.md"
---

# Specification: File Metadata and Relation Storage Layer

## Goal

Implement file metadata and relation storage layer in bensyne to connect memories (chunks) to their source files with file-level metadata, inter-file relationships, and source-type-specific enrichment. 20 tasks completed, 1335 tests passing.

## Architecture

Additive layer with 3 entities, 1 aggregate, SQLite per-bank storage, and file-centric MCP tools:

- **Domain:** File, FileChunk, FileRelation entities; FileMetadataAggregate; 4 domain events; 3 repository interfaces (collapsed to concrete types)
- **Infrastructure:** SQLAlchemy ORM (FileORM, FileChunkORM, FileRelationORM), SQLite per-bank (`file_metadata.db`), Alembic migrations (V1–V5), FTS5 search
- **Application:** FileService with mandatory structlog.BoundLogger, 8 use cases, ForgetMemoryUseCase with file cleanup
- **MCP Tools:** searchFiles, expandFileRelations, fetchFile, recallMemory (renamed), rememberMemory (renamed)
- **Integration:** Racochu FileMetadataPropagator with BensyneFileClient interface (43 integration tests)

## Phases Completed

1. **Domain Layer** — File, FileChunk, FileRelation entities with Pydantic validation; FileMetadataAggregate with chunk uniqueness and content composition; 3 domain interfaces; domain events (270 tests)
2. **Infrastructure** — SQLite Connection Manager (per-bank, WAL, pooling); 3 SQLite repos (FileRepositorySQLite with FTS5, FileChunkRepositorySQLite, FileRelationRepositorySQLite); Alembic migrations V1–V5 (156 tests)
3. **Application + MCP Tools** — FileService (8 methods, mandatory logger); searchFiles, expandFileRelations, fetchFile use cases; MCP tool registration; recallMemory/rememberMemory renaming (101 tests)
4. **Integration** — 43 integration tests across 7 test classes; Racochu FileMetadataPropagator with BensyneFileClient interface (22 tests)

## Risks

- SQLite cross-bank queries require external orchestration (mitigated: external orchestration is acceptable)
- Racochu integration complexity (mitigated: 43 integration tests with feature flag)
- File path handling edge cases (mitigated: normalized path storage, hash-based identifiers)

## Test Results

| Metric | Value |
|--------|-------|
| Tests | 1335 passing (unit + integration) |
| Integration Tests | 43 across 7 test classes |
| Pre-existing e2e errors | 25 (unrelated, memory bank routing) |
