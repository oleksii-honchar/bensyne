---
type: memory
title: "SSE Transport Deprecated"
createdAt: "2026-07-30T16:00:00Z"
updatedAt: "2026-08-16T00:00:00Z"
tags: [transport, mcp]
see_also: ["memories/0002-streamable-http-recommended.memory.md", "../../memories/0001-mcp-transport-sse-deprecated.memory.md"]
---

# Memory: SSE Transport Deprecated

## Fact

SSE (Server-Sent Events) transport is deprecated for Mnemosyne MCP communication due to reliability issues.

## Context

Investigation revealed:
- SSE is prone to init handshake races — clients send tool calls before server completes initialization
- Error "Received request before initialization was complete" caused by this race condition
- SSE is legacy technology with multiple failure points
- Fixing SSE is not recommended — technology is being superseded

## Impact

Migrate to Streamable HTTP transport (modern MCP standard) or stdio for reliable communication.

## Status Note

> **2026-08-16:** Merged into shared MEM-SYS-0001 (`../../memories/0001-mcp-transport-sse-deprecated.memory.md`) — the cross-system protocol-level memory; this node remains the bensyne-mcp system-specific record.
