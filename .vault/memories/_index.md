---
type: index
title: "Atomic Memories"
createdAt: "2026-08-01T21:31:00Z"
updatedAt: "2026-08-07T19:01:00Z"
tags: []
---

# Atomic Memories

Durable facts, gotchas, and operational learnings for Bensyne MCP server.

## Nodes

### Transport

- [[0001-sse-transport-deprecated]] — SSE transport is deprecated due to reliability issues
- [[0002-streamable-http-recommended]] — Streamable HTTP is recommended MCP transport

### File Hash Deduplication

- [[0003-bensyne-file-logging-rotation]] — bensyne.log at ~/.local/share/bensyne/logs/, 10 MB rotation, 3 backups
- [[0004-sqlite-wal-concurrent-reads]] — SQLite WAL mode allows concurrent reads during hash index writes; no read lockout
