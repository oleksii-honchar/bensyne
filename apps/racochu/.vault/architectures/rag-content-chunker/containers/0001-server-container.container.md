---
type: container
title: "RAG Content Chunker — Server Container"
c4_level: container
system: rag-content-chunker
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [architecture, container, nestjs]
see_also: ["adrs/0008-remote-database-segregation.adr.md"]
linked_elements: []
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Container: RAG Content Chunker — Server Container

## Diagram

```mermaid
C4Container
  title RAG Content Chunker — Container Level

  Person(operator, "Operator", "Configures watch sources, monitors operation")

  Boundary(rag, "RAG Content Chunker", "Boundary") {
    Container(server, "RAG Content Chunker Server", "Node.js + NestJS", "File watcher → Mastra chunking → Mnemosyne ingestion")
  }

  System_Ext(filesystem, "File System", "Watched directories (agent-sessions, obsidian, vault, etc.)")
  System_Ext(mnemosyne, "better-mnemosyne MCP Server", "Remote Mnemosyne MCP with namespace routing")

  Boundary(remote, "Remote Databases", "Boundary") {
    ContainerDb(db1, "agent-sessions.db", "SQLite", "Agent session memories")
    ContainerDb(db2, "obsidian.db", "SQLite", "Obsidian vault memories")
    ContainerDb(db3, "vault.db", "SQLite", "Vault knowledge memories")
  }

  Rel(operator, server, "Configures via", "~/.config/rag-content-chunker.yaml")
  Rel(server, filesystem, "Watches for changes", "Chokidar")
  Rel(server, mnemosyne, "Ingests chunks via", "Streamable HTTP MCP")
  Rel(mnemosyne, db1, "Routes by namespace")
  Rel(mnemosyne, db2, "Routes by namespace")
  Rel(mnemosyne, db3, "Routes by namespace")
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| `server` | RAG Content Chunker Server | Container | Node.js + NestJS 11 | Single-process CLI server: watches files, chunks via Mastra, enhances, ingests to Mnemosyne |
| `filesystem` | File System | System_Ext | — | Watched directories defined in config (up to multiple sources) |
| `mnemosyne` | better-mnemosyne MCP Server | System_Ext | Python + MCP | Remote namespace-aware Mnemosyne server; routes per namespace to separate SQLite DBs |

## Notes

- **Single-container design:** RAG Content Chunker is a single NestJS CLI process — no separate workers, APIs, or microservices
- **Transport:** Streamable HTTP (not SSE, not stdio) — SSE deprecated in Mnemosyne due to init handshake races
- **Ephemeral:** No database on RAG Content Chunker side — all state stored in remote Mnemosyne databases
- **Graceful shutdown:** SIGTERM/SIGINT → stop watchers → drain queue → close Mnemosyne client (30s timeout)
