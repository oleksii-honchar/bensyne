---
type: index
title: "Architectures"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-12T16:44:16Z"
tags: []
---

# Architectures

C4 architecture diagrams and structural documentation for Bensyne MCP server.

## Nodes

### bensyne

- [[bensyne/0001-container]] — Container-level: FastMCP Server (11 tools), MemoryBankRouter, Mnemosyne OSS library, HashIndex DB, FileMetadata DB, Racochu ingest
- [[bensyne/0001-component]] — Component-level: 4-layer hexagonal decomposition with file metadata components (FileMetadataAggregate, FileService, SQLite repos)
- [[bensyne/0001-code]] — Code-level: Memory domain model with entity-aggregate-value object relationships and event flows
- [[bensyne/0002-file-metadata]] — Code-level: FileMetadataAggregate, File, FileChunk, FileRelation entities, events, SQLite storage
