---
type: index
title: "Domain Concepts"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-12T16:58:00Z"
tags: []
---

# Domain Concepts

Core domain terminology and mental models for Bensyne MCP server.

## Nodes

### File Hash Deduplication

- [[0001-hash-index]] — SQLite HashIndex for file hash deduplication; used by bensyne handlers and racochu for cross-device sync

### DDD Domain Model

- [[0002-memory-domain]] — Memory entity: frozen dataclass with Pydantic validation, factory methods, invariants
- [[0003-memory-bank-aggregate]] — Aggregate root orchestrating MemoryBank + Memory with invariants and domain events

### File Metadata

- [[0004-file-metadata-aggregate]] — Aggregate root for file metadata: chunk uniqueness, content composition, event production
- [[0005-source-type-file-role]] — Source type taxonomy (agent_session/file_system/git/database/external/remote/unknown) and file type classification (config/code/docs)
- [[0006-file-chunk-relation]] — FileChunk (file-memory junction with positional metadata) and FileRelation (9 relation types with strength/direction)
- [[0007-file-metadata-layer]] — Architecture overview: 3-tier structure (domain/infrastructure/application), SQLite per-bank, custom migrations V1–V5, FTS5, MCP tools
