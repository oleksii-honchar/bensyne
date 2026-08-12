---
type: container
title: "Bensyne — Container Level"
c4_level: container
system: bensyne
createdAt: "2026-08-10T07:00:00Z"
updatedAt: "2026-08-12T16:44:16Z"
tags: [c4, container, architecture]
see_also:
  - "adrs/0007-ddd-migration-approach.adr.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
  - "concepts/0003-memory-bank-aggregate.concept.md"
linked_elements:
  - bensyne-mcp-server
  - mnemosyne-oss
  - hash-index-db
  - file-metadata-db
  - racochu-ingest
---

# Bensyne — Container Level

## Diagram

```mermaid
C4Container
  title Bensyne MCP Server — Container Level

  Person(agent, "AI Agent", "External AI agent using bensyne via MCP")

  System_Ext(racochu, "Racochu", "TypeScript/NestJS", "Source-aware ingestion — chunks files and propagates file metadata via BensyneFileClient")

  System_Boundary(bensyne, "Bensyne MCP Server") {
    Container(mcp_server, "FastMCP Server", "Python", "MCP protocol endpoint — 11 tools: rememberMemory, recallMemory, forgetMemory, updateMemory, sleep, getMemoryStats, listMemoryBanks, registerMemoryBank, searchFiles, expandFileRelations, fetchFile; stateless HTTP transport")
    Container(router, "MemoryBankRouter", "Python", "Manages per-bank MnemosyneClient instances with LRU eviction")
  }

  System_Ext(mnemosyne, "Mnemosyne OSS", "Python library", "Memory storage engine — provides remember/recall/forget/update/sleep/stats via library interface")

  ContainerDb(hash_index, "HashIndex DB", "SQLite", "File hash deduplication index — maps file hashes to memory IDs; uses WAL mode for concurrent reads", vault_link="concepts/0001-hash-index.concept.md")
  ContainerDb(file_metadata, "FileMetadata DB", "SQLite", "Per-bank file metadata — files, file_chunks, file_relations tables; WAL mode; FTS5 search", vault_link="concepts/0007-file-metadata-layer.concept.md")

  Rel(agent, mcp_server, "MCP Protocol", "HTTP/Streamable HTTP")
  Rel(racochu, mcp_server, "MCP tools/call — remember/recall + file metadata propagation", "HTTP")
  Rel(mcp_server, router, "Delegates per-bank operations", "Python in-process")
  Rel(router, mnemosyne, "Library calls", "Python in-process")
  Rel(mcp_server, hash_index, "Deduplication lookup", "SQLite WAL")
  Rel(mcp_server, file_metadata, "File metadata CRUD + FTS5 search", "SQLite WAL")
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| bensyne-mcp-server | FastMCP Server | Container | Python/FastMCP | MCP protocol endpoint exposing 11 memory + file tools; stateless HTTP |
| router | MemoryBankRouter | Container | Python | Per-bank instance pool with LRU eviction and MnemosyneClient management |
| mnemosyne-oss | Mnemosyne OSS | System_Ext | Python library | External memory storage engine (imported as library, not service) |
| hash-index-db | HashIndex DB | ContainerDb | SQLite | File hash deduplication index in WAL mode |
| file-metadata-db | FileMetadata DB | ContainerDb | SQLite | Per-bank file metadata store (files, file_chunks, file_relations) in WAL mode with FTS5 |
| racochu-ingest | Racochu | System_Ext | TypeScript/NestJS | Source-aware ingestion; propagates file metadata + chunk links via MCP |

## Notes

- bensyne imports mnemosyne as a Python library (`from mnemosyne import Mnemosyne`), not as a remote service
- Per-bank storage: `mnemosyne.db` (memories), `hash_index.db` (dedup), `file_metadata.db` (file metadata) — all in the bank's data directory
- MemoryBankRouter maintains a pool of MnemosyneClient instances with LRU eviction
- Racochu is the primary producer of file metadata (source-type enrichment lives there, per ADR-0013)
- Health endpoints: `/health`, `/health/ready`, `/health/log`; server runs with `stateless_http=True`
