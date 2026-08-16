---
type: memory
id: MEM-SYS-0002
title: "MCP Transport: Streamable HTTP Recommended"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [transport, mcp, memory-bank]
see_also:
  - "systems/bensyne-mcp/memories/0002-streamable-http-recommended.memory.md"
  - "systems/racochu/memories/0005-mnemosyne-client-streamable-http.memory.md"
  - "memories/0001-mcp-transport-sse-deprecated.memory.md"
---

# Memory: MCP Transport — Streamable HTTP Recommended

## Fact

Streamable HTTP transport is the recommended transport for MCP clients communicating with the Bensyne memory server (historically "Mnemosyne") — POST to the `/mcp` endpoint, not SSE or stdio. All new MCP clients should use it.

## Context

The RAG Content Chunker's `MnemosyneClient` (now `BensyneClient`) was rewritten from SSE to Streamable HTTP:

- Code reduced from 671 → ~160 lines
- Uses native `http`/`https` modules (no external HTTP client)
- Performs the MCP initialization handshake (`initialize` + `notifications/initialized`)
- Tracks session via `Mcp-Session-Id` header
- Bridges via mcp-proxy (sparfenyuk/mcp-proxy) for stdio→HTTP conversion
- Implements retry logic with exponential backoff for `remember()` operations
- Supports `remember()`, `recall()`, `forget()`, and memory-bank registration (`registerMemoryBank`; historically `registerNamespace()`)

## Per-System Experience

### bensyne-mcp

Server exposes the Streamable HTTP `/mcp` endpoint; SSE is deprecated (see MEM-SYS-0001). This transport is the standard for all clients of the memory server.

### racochu

`BensyneClient` runs entirely on Streamable HTTP; all E2E tests validate this transport via mcp-proxy. SSE's init-handshake races are gone.

## Impact

All new MCP clients should use Streamable HTTP transport. SSE should be avoided.

## Status Note

> **2026-08-16:** Merged from bensyne-mcp memory 0002 and racochu memory 0005 into this shared transport memory.
