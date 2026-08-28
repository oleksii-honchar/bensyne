---
type: index
title: "Memories"
createdAt: "2026-08-16"
updatedAt: "2026-08-28T17:23:01Z"
---

# Memories

Durable facts, lessons, and gotchas. Single ID space: `MEM-NNNN` (0001–0026). Grouped by `system` frontmatter.

### Shared

- [[0001-mcp-transport-sse-deprecated]] — MCP Transport — SSE Deprecated
- [[0002-mcp-transport-streamable-http]] — MCP Transport — Streamable HTTP Recommended
- [[0021-bensyne-forgetfile-tombstone]] — Bensyne forgetFile Leaves a DELETED Tombstone — Not a Hard Row Delete
- [[0024-mcp-tool-description-is-canonical-teaching-surface]] — MCP Tool Description Is the Canonical Teaching Surface
- [[0026-forgetfile-file-not-found-noop]] — forgetFile FILE_NOT_FOUND Is an Idempotent No-Op — Server Returns JSON Status

### bensyne-mcp

- [[0003-sse-transport-deprecated]] — SSE Transport Deprecated
- [[0004-streamable-http-recommended]] — Streamable HTTP Recommended Transport
- [[0005-bensyne-file-logging-rotation]] — Bensyne Log File Location and Rotation
- [[0006-sqlite-wal-concurrent-reads]] — HashIndex Uses SQLite WAL Mode for Concurrent Reads
- [[0007-on-conflict-do-update]] — Safe File Upserts — session.merge() over INSERT OR REPLACE
- [[0025-channel-weighting-makes-description-backfill-load-bearing]] — Channel Weighting Makes Description Backfill Load-Bearing

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
- [[0020-mnemosyne-valid-until-soft-expiry]] — Mnemosyne Native valid_until Is Soft Expiry — Not Per-Source Retention or Auto-Sweep
- [[0022-enrichment-chunkhash-invariant]] — Enrichment Never Rewrites Chunk Text — chunkHash Is Invariant
- [[0023-chokidar-dot-root-self-exclusion]] — Exclude Glob Matching the Watched Root (dot-named root self-exclusion)
