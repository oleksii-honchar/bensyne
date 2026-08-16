---
type: concept
title: "Chunk"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [domain, chunking]
see_also: ["adrs/0009-mastra-rag-integration.adr.md", "concepts/0003-enhancement-pipeline.concept.md"]
---

# Concept: Chunk

## What

A Chunk is the core domain entity representing a semantically coherent fragment of file content, ready for embedding and storage in Mnemosyne.

## Why

Files must be split into meaningful, self-contained units before ingestion — too large and embeddings lose precision; too small and semantic context is lost.

## Key Details

**Verified schema (src/domain/chunk.entity.ts):**
- `id` — UUID for deduplication and reference
- `text` — Chunk content (respects character limits: 200–400 per file role)
- `chunkIndex` / `totalChunks` — Position within source file sequence
- `sectionHeader` — Section context (from markdown headers or Mastra extraction)
- `fileRole` — One of: `config`, `code`, `docs`, `agent-output`
- `importance` — Score 0.0–1.0 (computed by ImportanceScoringService)
- `tags` — Up to 20 extracted tags for retrieval
- `namespace` — Mnemosyne namespace for server-side database routing
- `metadata` — Extensible: filePath, sourceId, language, line ranges

**Lifecycle:**
1. Created by MastraChunkingService from MDocument chunks
2. Enhanced by EnhancementPipelineService (importance + tags + namespace)
3. Stored via MnemosyneClient.remember() → Mnemosyne MCP → SQLite

**Not a:** Raw text snippet — a Chunk carries semantic context (header, role, metadata) and is validated via Zod schema.
