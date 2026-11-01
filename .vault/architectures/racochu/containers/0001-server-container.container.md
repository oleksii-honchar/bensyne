---
type: container
title: "RAG Content Chunker — Server Container"
c4_level: container
system: racochu
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [architecture, container, nestjs]
see_also: [decisions/0026-remote-database-segregation.decision.md, decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md, decisions/0120-prisma-migrate-deploy-with-fail-loud-dedup-guard.decision.md, decisions/0121-manual-cli-watch-operation-with-instance-lock.decision.md, concepts/0014-file-memory-tracking.concept.md]
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
    Container(server, "RAG Content Chunker Server", "Node.js + NestJS", "File watcher → hash-gated ingest → Mastra chunking → Mnemosyne ingestion")
    ContainerDb(trackerDb, "racochu.db", "SQLite + Prisma migrations", "Local FileTracker/FileMemoryTracker state — dedup + final-decision store; migrate deploy at startup with row-count guard (DEC-0120)")
  }

  System_Ext(filesystem, "File System", "Watched directories (agent-sessions, obsidian, vault, etc.)")
  System_Ext(mnemosyne, "better-mnemosyne MCP Server", "Remote Mnemosyne MCP with namespace routing")

  Boundary(remote, "Remote Databases", "Boundary") {
    ContainerDb(db1, "agent-sessions.db", "SQLite", "Agent session memories")
    ContainerDb(db2, "obsidian.db", "SQLite", "Obsidian vault memories")
    ContainerDb(db3, "vault.db", "SQLite", "Vault knowledge memories")
  }

  Rel(operator, server, "Configures via", "~/.config/rag-content-chunker.yaml")
  Rel(operator, server, "Starts manually (no daemon, DEC-0121)", "CLI: watch / --resume / recover")
  Rel(server, filesystem, "Watches for changes", "Chokidar")
  Rel(server, trackerDb, "Reads/writes tracker state; watch lock data/racochu.watch.lock", "Prisma + better-sqlite3")
  Rel(server, mnemosyne, "Ingests chunks via", "Streamable HTTP MCP")
  Rel(mnemosyne, db1, "Routes by namespace")
  Rel(mnemosyne, db2, "Routes by namespace")
  Rel(mnemosyne, db3, "Routes by namespace")
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| `server` | RAG Content Chunker Server | Container | Node.js + NestJS 11 | Single-process CLI server: watches files, content-hash-gates the ingest decision (DEC-0119), chunks via Mastra, enhances, ingests to Mnemosyne |
| `trackerDb` | racochu.db | ContainerDb | SQLite (Prisma + better-sqlite3, N-API) | Local tracker state: `FileTracker` (final-decision store incl. `fileHash`, `skipReason`) + `FileMemoryTracker`; schema managed by committed migrations at startup with a fail-loud dedup row-count guard (DEC-0120) |
| `filesystem` | File System | System_Ext | — | Watched directories defined in config (up to multiple sources) |
| `mnemosyne` | better-mnemosyne MCP Server | System_Ext | Python + MCP | Remote namespace-aware Mnemosyne server; routes per namespace to separate SQLite DBs |

## Notes

- **Single-container design:** RAG Content Chunker is a single NestJS CLI process — no separate workers, APIs, or microservices
- **Transport:** Streamable HTTP (not SSE, not stdio) — SSE deprecated in Mnemosyne due to init handshake races
- **Stateful-local (corrected 2026-11-01):** an earlier note said "no database on the RAG Content Chunker side" — outdated: `data/racochu.db` (Prisma SQLite) has held FileTracker/FileMemoryTracker state since the tracking feature and is now the load-bearing dedup + final-decision store (DEC-0119/DEC-0120). Memories themselves stay remote in Mnemosyne. Runtime artifacts: watch single-instance lock `data/racochu.watch.lock` (DEC-0121), committed schema migrations `prisma/migrations/` applied at startup (DEC-0120).
- **Operating model:** operator-run CLI, no daemon (DEC-0121) — overlapping second watchers are refused by the lock; one-shot modes may overlap.
- **Graceful shutdown:** SIGTERM/SIGINT → stop watchers → drain queue → close Mnemosyne client (30s timeout)
