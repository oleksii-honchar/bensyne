---
type: index
title: "Architectures"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-12T00:00:00Z"
tags: []
---

# Architectures

C4 architecture diagrams and structural documentation for Bensyne MCP server.

## Nodes

### bensyne

- [[bensyne/0001-container]] — Container-level: FastMCP Server, MemoryBankRouter, Mnemosyne OSS library, HashIndex DB
- [[bensyne/0001-component]] — Component-level: 4-layer hexagonal decomposition (Adapters, Application, Domain, Infrastructure) with inter-component flows
- [[bensyne/0001-code]] — Code-level: Domain model with entity-aggregate-value object relationships, field schemas, and event flows
- [[bensyne/0002-file-metadata]] — Code-level: FileMetadataAggregate, File, FileChunk, FileRelation entities and domain events
