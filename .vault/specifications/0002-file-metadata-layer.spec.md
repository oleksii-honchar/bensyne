---
type: specification
kind: feature
system: bensyne-mcp
title: "File Metadata and Relation Storage Layer"
status: completed
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-18T07:55:43Z"
owner: ""
target: null
see_also:
  - concepts/0023-materialization.concept.md
  - decisions/0013-sqlite-file-metadata-storage.decision.md
  - decisions/0014-standalone-file-entities.decision.md
  - decisions/0015-file-specific-mcp-tools.decision.md
  - decisions/0016-racochu-source-enrichment.decision.md
  - decisions/0017-file-content-reconstruction.decision.md
  - concepts/0004-file-metadata-aggregate.concept.md
  - concepts/0007-file-metadata-layer.concept.md
---

# Specification: File Metadata and Relation Storage Layer

## Goal

Implement file metadata and relation storage layer in bensyne to connect memories (chunks) to their source files with file-level metadata, inter-file relationships, and source-type-specific enrichment. 20 tasks completed, 1352 tests collected.

**Status note (2026-08-18, unified write path D17–D29):** `FileMetadata` (renamed from `FileMetadataAggregate`) is again the SOLE write root — dead aggregate-CRUD universe deleted, materialization re-expressed on the aggregate; public write surface = `materialize_file_context` / `update_file` / `remove_chunk` / `delete_file` / `rebuild_projection`. Migrations collapsed to a single bootstrap (D28). Source-type value axis redefined as real producers, strategy ≡ type (D29). See [[0023-materialization]] for the concept.

## Architecture

Additive layer with 3 entities, 1 aggregate, SQLite per-bank storage, and file-centric MCP tools:

- **Domain:** File, FileChunk, FileRelation entities; `FileMetadata` aggregate (renamed from FileMetadataAggregate, 2026-08-18); domain events (file events + chunk/relation events); repository interfaces collapsed to concrete types
- **Infrastructure:** SQLAlchemy ORM (FileORM, FileChunkORM, FileRelationORM), SQLite per-bank (`file_metadata.db`), **single bootstrap migration** (`file_metadata_migrations.py`; legacy V1–V6 collapsed, D28 — byte-identical final schema + schema-snapshot guard, no upgrade path), FTS5 search
- **Application:** FileService with mandatory structlog.BoundLogger, use cases, ForgetMemoryUseCase with file cleanup
- **MCP Tools:** searchFiles, expandFileRelations, fetchFile, recallMemory (renamed), rememberMemory (renamed)
- **Integration:** ~~Racochu FileMetadataPropagator with BensyneFileClient interface~~ — **deleted** (cornerstone, 2026-08-16); racochu enriches via remember-memory metadata — enrichment travels the remember wire

## Phases Completed

1. **Domain Layer** — File, FileChunk, FileRelation entities with Pydantic validation; FileMetadataAggregate with chunk uniqueness and content composition; domain events (270 tests)
2. **Infrastructure** — SQLite Connection Manager (per-bank, WAL, pooling); 3 SQLite repos (FileRepository, FileChunkRepository, FileRelationRepository); custom migrations V1–V5 (156 tests)
3. **Application + MCP Tools** — FileService (aggregate-based); searchFiles, expandFileRelations, fetchFile use cases; MCP tool registration; recallMemory/rememberMemory renaming (101 tests)
4. **Integration** — 43 integration tests across 7 test classes; Racochu FileMetadataPropagator with BensyneFileClient interface (22 tests)

## Risks

- SQLite cross-bank queries require external orchestration (mitigated: external orchestration is acceptable)
- Racochu integration complexity (mitigated: 43 integration tests with feature flag)
- File path handling edge cases (mitigated: normalized path storage, hash-based identifiers)

## Test Results

| Metric | Value |
|--------|-------|
| Tests | 1352 collected (unit + integration) |
| Integration Tests | 43 across 7 test classes |
| Pre-existing e2e errors | 25 (unrelated, memory bank routing) |
