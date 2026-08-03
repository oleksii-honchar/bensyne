---
type: memory
title: "Streamable HTTP Recommended Transport"
createdAt: "2026-07-30T18:00:00Z"
updatedAt: "2026-07-30T18:00:00Z"
tags: [transport, mcp]
see_also: ["memories/0001-sse-transport-deprecated.memory.md"]
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
