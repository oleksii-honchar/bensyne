---
type: index
title: "Atomic Memories"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-09T19:30:00Z"
tags: []
---

# Atomic Memories

Durable facts, gotchas, and operational learnings for RAG Content Chunker.

## Nodes

### Mnemosyne MCP

- [[0001-mnemosyne-sse-deprecated]] — SSE transport is legacy; prefer Streamable HTTP
- [[0002-mnemosyne-schema-versioning]] — Stale DB causes "no such column: timestamp"
- [[0003-mnemosyne-dedup-inmemory-reset]] — In-memory dedup resets on restart
- [[0004-mcp-proxy-transport-switch]] — Proxy solution for stdio→HTTP bridge in e2e tests
- [[0005-mnemosyne-client-streamable-http]] — MnemosyneClient transport switch to Streamable HTTP via mcp-proxy

### File Update Flow

- [[0006-change-handler-per-id-forget-memory]] — handleChange uses per-ID forgetMemories (not deleteByFilePath) to preserve new tracker entries
- [[0007-chokidar-macos-dual-events]] — macOS chokidar fires duplicate events; processing Set deduplicates

### Hash Deduplication

- [[0008-sha256-collision-negligible]] — SHA-256 collision probability is 2^-128, negligible for any practical workload

### LLM Enrichment

- [[0009-mastra-extract-metadata-basellm-hardcoded]] — Mastra's extractMetadata() hardcodes OpenAI as baseLLM; custom LLM required via llm parameter
- [[0010-custom-gateway-superseded-by-mastra-llm]] — Custom LiteLLMHttpClient + EnrichmentGatewayService replaced by Mastra's llm parameter approach
- [[0012-enrichment-metadata-not-indexed]] — Mnemosyne doesn't index metadata_json — enrichment pipeline is basically useless for search

### Obsidian

- [[0011-typed-keys-casing-typed-key-leakage]] — TYPED_KEYS casing fix — capitalized keys leak into properties
