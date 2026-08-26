---
type: memory
system: racochu
title: "Enrichment Never Rewrites Chunk Text — chunkHash Is Invariant"
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [enrichment, chunkhash, dedup, invariant]
see_also:
  - decisions/0080-recover-skipenrichment-chunking.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - concepts/0021-llm-enrichment.concept.md
  - concepts/0025-cheap-chunk-verification.concept.md
---

# Memory: Enrichment Never Rewrites Chunk Text — chunkHash Is Invariant

## Fact

`metadata.chunkHash` is the sha256 of the exact chunk text and is computed **after** enrichment
in `ChunkContentUseCase`. Enrichment (`EnhancementPipelineService.enhance` + Mastra
`extractMetadata`) only mutates metadata (importance, tags, title, keywords, summary) — never
chunk text.

## Context

Verified during the recover-mode design (2026-08-25): `EnhancementPipelineService.enhance` is
local heuristics, not an LLM call; the Mastra `extractMetadata` block is the only LLM enrichment
cost. This invariant is what makes enrichment-free chunking (`skipEnrichment`) produce hashes
comparable with enriched ingests.

## Impact

- Recover's verification path can chunk without enrichment and still compare `chunk_hash`
  against stored `content_hash` values from enriched ingests.
- Dedup keys stay stable regardless of whether enrichment was enabled at ingest time.
