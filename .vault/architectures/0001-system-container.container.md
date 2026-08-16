---
type: container
title: "Bensyne Monorepo — System Container (bensyne-mcp + racochu)"
c4_level: container
system: bensyne-monorepo
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [architecture, container, mcp, streamable-http]
see_also:
  - decisions/0001-namespace-registration-protocol.decision.md
  - memories/0002-mcp-transport-streamable-http.memory.md
  - architectures/racochu/containers/0001-server-container.container.md
  - architectures/bensyne-mcp/_index.md
  - architectures/racochu/_index.md
linked_elements: []
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Container: Bensyne Monorepo — System Container (bensyne-mcp + racochu)

Whole-system container view spanning both apps and the MCP protocol boundary between them. Rendered as PNG (diagram validation uses `format: "png"` — never SVG).

## Diagram

```mermaid
C4Container
  title Bensyne Monorepo — Container Level (bensyne-mcp + racochu + MCP protocol boundary)

  Person(agent, "AI Agent", "Recalls, remembers, and explores memories and files via MCP tools")

  Boundary(racochu, "racochu — Ingestion Server", "Node.js + NestJS 11") {
    Container(chunker, "RAG Content Chunker", "Node.js + NestJS", "Watches directories, semantically chunks via Mastra RAG, enriches by source type, ingests into the memory server")
    Container(bensyneclient, "BensyneClient", "TypeScript", "MCP client over Streamable HTTP (native http/https, mcp-proxy stdio bridge)")
  }

  Boundary(mcp, "MCP Protocol Boundary", "Streamable HTTP transport (POST /mcp) — SSE deprecated") {
    Container(mcptransport, "Streamable HTTP Transport", "MCP over HTTP", "MCP initialization handshake, Mcp-Session-Id session tracking, retry with exponential backoff")
  }

  Boundary(bensynemcp, "bensyne-mcp — Memory Server", "Python + FastMCP") {
    Container(server, "Bensyne MCP Server", "Python + FastMCP", "Memory banks, file metadata layer, MCP tools (registerMemoryBank, rememberMemory, recallMemory, searchFiles, expandFileRelations, fetchFile)")
    ContainerDb(banks, "Memory bank databases", "SQLite (WAL mode)", "Per-memory-bank memories and file metadata (files, file_chunks, file_relations, FTS5)")
  }

  System_Ext(filesystem, "File System", "Watched source directories (agent-sessions, obsidian, vault, ...)")

  Rel(agent, mcptransport, "Calls MCP tools via", "Streamable HTTP (POST /mcp)")
  Rel(chunker, bensyneclient, "Ingests via", "remember() / recall() / forget() / registerMemoryBank()")
  Rel(bensyneclient, mcptransport, "Speaks MCP over", "Streamable HTTP (mcp-proxy bridges stdio)")
  Rel(mcptransport, server, "Delivers MCP requests to", "FastMCP tool handlers")
  Rel(chunker, filesystem, "Watches for changes", "Chokidar")
  Rel(server, banks, "Reads/writes per memory bank", "SQLAlchemy ORM, session.merge() upserts")
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| `agent` | AI Agent | Person | — | Consumes memories and files through MCP tools |
| `chunker` | RAG Content Chunker | Container | Node.js + NestJS 11 | racochu server: watches sources, chunks via Mastra RAG, enriches, ingests |
| `bensyneclient` | BensyneClient | Component | TypeScript | racochu's MCP client — Streamable HTTP, native `http`/`https`, mcp-proxy bridge |
| `mcptransport` | Streamable HTTP Transport | Container | MCP over HTTP | The protocol boundary — handshake, session tracking, retry; SSE deprecated |
| `server` | Bensyne MCP Server | Container | Python + FastMCP | Memory bank + file metadata server exposing the MCP tools |
| `banks` | Memory bank databases | ContainerDb | SQLite (WAL) | Per-bank storage for memories and file metadata |
| `filesystem` | File System | System_Ext | — | Watched source directories defined in racochu config |

## Notes

- **Transport:** Streamable HTTP is the only supported remote transport across the MCP boundary — SSE was deprecated due to init handshake races (see `memories/0001-mcp-transport-sse-deprecated.memory.md`); mcp-proxy bridges stdio→HTTP where needed (e.g. e2e tests).
- **Protocol decisions:** memory bank registration (DEC-0001), bank parameter enforcement (DEC-0002), and in-memory bank registry (DEC-0003) live at the vault root `decisions/` area.
- **Ephemeral racochu side:** no durable database on the racochu side — all state is stored in bensyne-mcp's per-bank SQLite databases.
- **Per-system detail:** see `architectures/racochu/` (component level) and `architectures/bensyne-mcp/`.
