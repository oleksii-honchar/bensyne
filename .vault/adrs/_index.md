---
type: index
title: "Architecture Decision Records"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: []
---

# Architecture Decision Records

Curated list of architectural decisions for Bensyne MCP server.

## Nodes

### Namespace Management

- [[0001-namespace-registration-tool]] — Add register_namespace tool for external systems to self-describe namespaces
- [[0002-namespace-parameter-enforcement]] — Make namespace required for all memory tools
- [[0003-in-memory-namespace-registry]] — In-memory registry for namespace descriptions
- [[0004-namespace-enforcement-breaking-change]] — Hard enforcement strategy for namespace requirement

### File Hash Deduplication

- [[0005-sqlite-hash-index]] — SQLite HashIndex for file hash deduplication (Mnemosyne lacks triple store API)

### Logging

- [[0006-rotating-file-handler-logging]] — RotatingFileHandler for persistent application logging (10 MB rotation, 3 backups)

### DDD Migration

- [[0007-ddd-migration-approach]] — Adopt Python DDD patterns while keeping the Python language stack
- [[0008-result-pattern-error-handling]] — Result[T] pattern with domain events for explicit error handling
- [[0009-pydantic-validation]] — Pydantic for data validation in domain entity factory methods

### File Metadata

- [[0010-sqlite-file-metadata-storage]] — SQLite per bank for file metadata storage (follows hash index pattern)
- [[0011-standalone-file-entities]] — Standalone File entities with FileChunk junction (not embedded in Memory)
- [[0012-file-specific-mcp-tools]] — File-specific MCP tools (searchFiles, fetchFile, expandFileRelations) alongside memory tools
- [[0013-racochu-source-enrichment]] — Source-type enrichment in Racochu; bensyne remains source-agnostic
- [[0014-file-content-reconstruction]] — File content reconstruction from chunks with chunk_index ordering
- [[0015-on-conflict-do-update]] — ON CONFLICT DO UPDATE for file upserts (not INSERT OR REPLACE — prevents chunk loss)
