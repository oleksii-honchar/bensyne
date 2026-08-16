---
type: memory
id: MEM-0001
system: shared
title: "MCP Transport: SSE Deprecated"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: [transport, mcp, memory-bank]
see_also:
  - memories/0003-sse-transport-deprecated.memory.md
  - memories/0008-mnemosyne-sse-deprecated.memory.md
  - memories/0002-mcp-transport-streamable-http.memory.md
---

# Memory: MCP Transport — SSE Deprecated

## Fact

SSE (Server-Sent Events) transport is deprecated for MCP communication with the Bensyne memory server (historically "Mnemosyne") due to reliability issues. All MCP clients should use Streamable HTTP (or stdio for local use).

## Context

Investigation revealed:

- SSE is prone to init handshake races — clients send tool calls before the server completes initialization
- Error "Received request before initialization was complete" caused by this race condition
- SSE is legacy technology with multiple failure points
- Fixing SSE is not recommended — the technology is being superseded

## Per-System Experience

### bensyne-mcp

The server-side investigation that established the deprecation: SSE failure points and handshake races; conclusion — migrate clients to Streamable HTTP or stdio.

### racochu

The RAG Content Chunker switched off SSE to Streamable HTTP via mcp-proxy (bridging stdio→HTTP for e2e tests). After the switch: 6/6 e2e tests pass, no more `session_id` race errors. All its MCP communication uses Streamable HTTP.

## Impact

Migrate to Streamable HTTP transport (modern MCP standard) or stdio for reliable communication. SSE should be avoided in all new MCP clients.

## Status Note

> **2026-08-16:** Merged from bensyne-mcp memory 0001 and racochu memory 0001 into this shared transport memory.
