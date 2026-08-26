---
type: decision
id: DEC-0081
system: racochu
title: "Enrichment-Free Chunking via Explicit skipEnrichment Flag"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, chunking, enrichment, verification, zero-llm]
supersedes: []
superseded_by: []
see_also:
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - decisions/0047-disable-enrichment-by-default.decision.md
  - concepts/0021-llm-enrichment.concept.md
  - concepts/0013-mastra-chunking-strategies.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
  - memories/0022-enrichment-chunkhash-invariant.memory.md
---

# DEC-0081: Enrichment-Free Chunking via Explicit skipEnrichment Flag

## Context

The recover verification pass must enumerate chunks cheaply — no per-chunk summarization. The
LLM cost is the Mastra `extractMetadata` per-chunk block, gated by
`enrichmentConfig.enabled && llmUrl && apiKey` in `MastraChunkingService.chunkFile`.
`EnhancementPipelineService.enhance` is verified to be local heuristics (importance + tags), not
an LLM call. Recover must force the cheap path regardless of runtime config.

## Decision

Add optional `skipEnrichment?: boolean` to `ChunkContentUseCase` params (default `false`). When
true: skip `enhancementPipelineService.enhance` and pass a skip override into
`MastraChunkingService.chunkFile` so the `extractMetadata` LLM block is skipped even if config
enables it. Enrichment never rewrites chunk text, so `metadata.chunkHash` (sha256 of exact text)
is identical with or without enrichment — hashes stay comparable with enriched ingests.

**Signature-correction vs draft:** the override is the optional **5th parameter** of
`BaseChunkingStrategy.chunkFile(content, filePath, sourceId, sourceConfig, options?)` — NOT 4th,
which is already `sourceConfig` at the call site (a 4th-position flag would silently receive the
config object and force enrichment on).

## Alternatives Considered

- Read config and branch on `enrichment.enabled` — rejected: recover must work even when
  enrichment is on; fragile if config changes mid-run.
- Separate "dry chunker" service — rejected: duplicates chunking logic; a flag on the existing
  use case is minimal.

## Consequences

- `BaseChunkingStrategy` gains an optional 5th param (other strategies unaffected — no LLM there).
- `ChunkContentUseCase` gains `skipEnrichment` zod param; verified in code.
