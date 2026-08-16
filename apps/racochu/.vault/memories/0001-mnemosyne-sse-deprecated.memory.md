---
type: memory
title: "Mnemosyne SSE transport deprecated"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [mnemosyne, mcp, transport]
see_also: ["runbooks/0003-troubleshooting.runbook.md"]
---

# Mnemosyne SSE Transport Deprecated

**Fact:** Mnemosyne MCP server's SSE transport is deprecated. RAG Content Chunker uses Streamable HTTP transport via mcp-proxy.

**Context:** SSE had race conditions during init handshake ("Received request before initialization was complete"). Solution: streamable HTTP server with mcp-proxy bridging stdio→HTTP for e2e tests.

**Impact:** 6/6 e2e tests now pass; no more session_id race errors. All MCP communication uses Streamable HTTP.
