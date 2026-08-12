---
type: concept
title: "File Metadata Layer Architecture Overview"
createdAt: "2026-08-12T00:00:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: [architecture, file-metadata, layer, storage, mcp-tools]
see_also:
  - "adrs/0010-sqlite-file-metadata-storage.adr.md"
  - "adrs/0011-standalone-file-entities.adr.md"
  - "adrs/0012-file-specific-mcp-tools.adr.md"
  - "adrs/0013-racochu-source-enrichment.adr.md"
  - "concepts/0004-file-metadata-aggregate.concept.md"
  - "specifications/0002-file-metadata-layer.spec.md"
---

# Concept: File Metadata Layer Architecture Overview

## What

The file metadata layer is an additive layer to bensyne that tracks file-level metadata, file-chunk relationships, and inter-file relationships. It sits between the racochu ingestion pipeline and the bensyne memory store.

**Three-tier structure:**
1. **Domain** — File, FileChunk, FileRelation entities; FileMetadataAggregate; domain events
2. **Infrastructure** — SQLite per-bank storage (`file_metadata.db`), SQLAlchemy ORM models, Alembic migrations, FTS5 search
3. **Application** — FileService (aggregate-based orchestration), use cases, MCP tool handlers

## Why

Before this layer, memories (content chunks) had no file context. File paths, source types, and relationships were lost when content was stored in mnemosyne. This layer restores that context while keeping the Memory entity clean and focused on memory semantics.

## Key Details

- **Storage:** SQLite per memory bank (`file_metadata.db`), WAL mode, connection pooling
- **Migrations:** Alembic with 5 versions (V1: files, V2: file_chunks, V3: file_relations, V4: FTS5, V5: summary field)
- **Search:** FTS5 full-text search on file path, keywords, and tags
- **MCP Tools:**
  - `searchFiles` — two-phase search (mnemosyne recall → file metadata enrichment)
  - `expandFileRelations` — relation expansion with summary_only mode
  - `fetchFile` — file reconstruction from chunks
- **Integration:** Racochu's FileMetadataPropagator with BensyneFileClient interface
- **Backward compatible:** Existing memories and operations unaffected
- **1335 tests passing** (unit + integration + 43 integration tests across 7 test classes)
