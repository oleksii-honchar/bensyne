---
type: memory
system: racochu
title: "mcp-proxy transport switch — stdio to HTTP"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [mcp, transport, e2e]
see_also: [memories/0008-mnemosyne-sse-deprecated.memory.md]
---

# mcp-proxy Transport Switch

**Fact:** E2E tests use mcp-proxy to bridge Mnemosyne MCP server's stdio transport to HTTP for the client.

**Context:** Mnemosyne server runs as MCP with stdio transport. Chunker needs HTTP transport. mcp-proxy bridges the gap for testing without changing server transport mode.

**Impact:** Test setup depends on mcp-proxy + correct JSON config. Production uses direct Streamable HTTP to Mnemosyne server.
