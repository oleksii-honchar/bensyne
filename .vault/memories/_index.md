---
type: index
title: "Shared Transport Memories"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: []
---

# Shared Transport Memories

Cross-system durable facts and lessons for the Bensyne monorepo — MCP transport between bensyne-mcp and racochu. ID series: `MEM-SYS-NNNN`. Per-system memories live under `systems/bensyne-mcp/memories/` and `systems/racochu/memories/`.

## Nodes

### MCP Transport

- [[0001-mcp-transport-sse-deprecated]] (MEM-SYS-0001) — SSE transport deprecated: init handshake races; use Streamable HTTP or stdio
- [[0002-mcp-transport-streamable-http]] (MEM-SYS-0002) — Streamable HTTP is the recommended MCP transport (POST /mcp, Mcp-Session-Id, mcp-proxy bridge)
