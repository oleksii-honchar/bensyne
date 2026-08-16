---
type: index
title: "Memories"
createdAt: "2026-08-16"
updatedAt: "2026-08-16"
tags: []
---

# Memories

Durable facts, lessons, and gotchas. Single ID space: `MEM-NNNN` (0001–0019). Grouped by `system` frontmatter.

### Shared

- [[0001-mcp-transport-sse-deprecated]] — MCP Transport — SSE Deprecated
- [[0002-mcp-transport-streamable-http]] — MCP Transport — Streamable HTTP Recommended

### bensyne-mcp

- [[0003-sse-transport-deprecated]] — SSE Transport Deprecated
- [[0004-streamable-http-recommended]] — Streamable HTTP Recommended Transport
- [[0005-bensyne-file-logging-rotation]] — Bensyne Log File Location and Rotation
- [[0006-sqlite-wal-concurrent-reads]] — HashIndex Uses SQLite WAL Mode for Concurrent Reads
- [[0007-on-conflict-do-update]] — Safe File Upserts — session.merge() over INSERT OR REPLACE

### racochu

- [[0008-mnemosyne-sse-deprecated]] — Mnemosyne SSE Transport Deprecated
- [[0009-mnemosyne-schema-versioning]] — Mnemosyne SQLite Schema Versioning Gotcha
- [[0010-mnemosyne-dedup-inmemory-reset]] — Mnemosyne Dedup In-Memory Reset
- [[0011-mcp-proxy-transport-switch]] — mcp-proxy Transport Switch
- [[0012-mnemosyne-client-streamable-http]] — MnemosyneClient Uses Streamable HTTP Transport
- [[0013-change-handler-per-id-forget-memory]] — handleChange Per-ID forgetMemories Bug Fix
- [[0014-chokidar-macos-dual-events]] — Chokidar Dual Events on macOS
- [[0015-sha256-collision-negligible]] — SHA-256 Collision Probability is Negligible
- [[0016-mastra-extract-metadata-basellm-hardcoded]] — Mastra extractMetadata() Hardcodes OpenAI baseLLM
- [[0017-custom-gateway-superseded-by-mastra-llm]] — Custom LiteLLM Gateway Superseded by Mastra llm Parameter
- [[0018-typed-keys-casing-typed-key-leakage]] — TYPED_KEYS Casing Fix — Capitalized Keys Leak into Properties
- [[0019-enrichment-metadata-not-indexed]] — Enrichment Metadata Not Indexed — Enrichment Pipeline Is Basically Useless
