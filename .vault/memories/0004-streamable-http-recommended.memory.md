---
type: memory
system: bensyne-mcp
title: "Streamable HTTP Recommended Transport"
createdAt: "2026-07-30T18:00:00Z"
updatedAt: "2026-08-16T00:00:00Z"
tags: [transport, mcp]
see_also: [memories/0003-sse-transport-deprecated.memory.md, memories/0002-mcp-transport-streamable-http.memory.md]
---

# Memory: Streamable HTTP Recommended Transport

## Fact

Streamable HTTP transport is the recommended transport for MCP clients communicating with Mnemosyne server.

## Context

RAG Content Chunker's MnemosyneClient was rewritten from SSE to Streamable HTTP:
- Code reduced from 671→~160 lines
- Uses native http/https modules (no external client)
- Handles MCP initialization handshake properly
- Supports session tracking via Mcp-Session-Id header
- Bridges via mcp-proxy (sparfenyuk/mcp-proxy) for stdio→HTTP conversion

## Impact

All new MCP clients should use Streamable HTTP transport. SSE should be avoided.

## Status Note

> **2026-08-16:** Merged into shared MEM-0002 (`../../memories/0002-mcp-transport-streamable-http.memory.md`) — the cross-system protocol-level memory; this node remains the bensyne-mcp system-specific record.
