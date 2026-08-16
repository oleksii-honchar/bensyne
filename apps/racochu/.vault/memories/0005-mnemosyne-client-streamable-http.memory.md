---
type: memory
title: "MnemosyneClient Uses Streamable HTTP Transport"
createdAt: "2026-07-30T18:00:00Z"
updatedAt: "2026-07-30T18:00:00Z"
tags: [mnemosyne, transport, mcp]
see_also: ["memories/0001-mnemosyne-sse-deprecated.memory.md", "memories/0004-mcp-proxy-transport-switch.memory.md"]
---

# Memory: MnemosyneClient Uses Streamable HTTP Transport

## Fact

MnemosyneClient communicates with better-mnemosyne MCP server via Streamable HTTP transport (POST to /mcp endpoint), not SSE or stdio. This was implemented via mcp-proxy bridging stdio→HTTP.

## Context

The MnemosyneClient was rewritten from SSE to Streamable HTTP (671→~160 lines). Key implementation details:
- Uses native `http`/`https` modules (no external HTTP client)
- Performs MCP initialization handshake (`initialize` + `notifications/initialized`)
- Tracks session via `Mcp-Session-Id` header
- Implements retry logic with exponential backoff for `remember()` operations
- Supports `remember()`, `recall()`, `forget()`, `registerNamespace()` methods

## Impact

SSE transport was legacy and prone to init handshake races. Streamable HTTP is more reliable and aligns with modern MCP transport standards. All E2E tests validate this transport via mcp-proxy.
