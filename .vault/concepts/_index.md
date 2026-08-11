---
type: index
title: "Domain Concepts"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-10T22:15:00Z"
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
