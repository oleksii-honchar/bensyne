---
type: container
title: "Bensyne — Container Level"
c4_level: container
system: bensyne
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-10T07:00:00Z"
tags: [c4, container, architecture]
see_also:
  - "adrs/0007-ddd-migration-approach.adr.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
  - "concepts/0003-memory-bank-aggregate.concept.md"
linked_elements:
  - bensyne-mcp-server
  - mnemosyne-oss
  - hash-index-db
---

# Bensyne — Container Level

## Diagram

```mermaid
C4Container
  title Bensyne MCP Server — Container Level

  Person(agent, "AI Agent", "External AI agent using bensyne via MCP")

  System_Boundary(bensyne, "Bensyne MCP Server") {
    Container(mcp_server, "FastMCP Server", "Python", "MCP protocol endpoint — handles remember, recall, forget, update, sleep, list_banks, register_bank tools")
    Container(router, "MemoryBankRouter", "Python", "Manages per-bank MnemosyneClient instances with LRU eviction")
  }

  System_Ext(mnemosyne, "Mnemosyne OSS", "Python library", "Memory storage engine — provides remember/recall/forget/update/sleep/stats via library interface")

  ContainerDb(hash_index, "HashIndex DB", "SQLite", "File hash deduplication index — maps file hashes to memory IDs; uses WAL mode for concurrent reads", vault_link="concepts/0001-hash-index.concept.md")

  Rel(agent, mcp_server, "MCP Protocol", "HTTP/Streamable HTTP")
  Rel(mcp_server, router, "Delegates per-bank operations", "Python in-process")
  Rel(router, mnemosyne, "Library calls", "Python in-process")
  Rel(mcp_server, hash_index, "Deduplication lookup", "SQLite WAL")
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| bensyne-mcp-server | FastMCP Server | Container | Python/FastMCP | MCP protocol endpoint exposing memory operations as tools |
| router | MemoryBankRouter | Container | Python | Per-bank instance pool with LRU eviction and MnemosyneClient management |
| mnemosyne-oss | Mnemosyne OSS | System_Ext | Python library | External memory storage engine (imported as library, not service) |
| hash-index-db | HashIndex DB | ContainerDb | SQLite | File hash deduplication index in WAL mode |

## Notes

- bensyne imports mnemosyne as a Python library (`from mnemosyne import Mnemosyne`), not as a remote service
- HashIndex uses SQLite in WAL mode — allows concurrent reads during writes (verified per [[0004-sqlite-wal-concurrent-reads]])
- MemoryBankRouter maintains a pool of MnemosyneClient instances with LRU eviction
- DDD migration added Result pattern, use cases, and domain layer; MCP tool interfaces preserved for backward compatibility
