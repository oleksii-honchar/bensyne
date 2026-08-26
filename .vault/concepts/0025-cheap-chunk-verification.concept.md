---
type: concept
system: shared
title: "Cheap Chunk Verification (Zero-LLM Recovery)"
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [verification, recover, zero-llm, chunk-set, hash]
see_also:
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - decisions/0080-recover-skipenrichment-chunking.decision.md
  - decisions/0085-recover-memory-status-point-reads.decision.md
  - concepts/0001-hash-index.concept.md
  - concepts/0020-file-hash-deduplication.concept.md
  - concepts/0008-chunk-concept.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# Concept: Cheap Chunk Verification (Zero-LLM Recovery)

## What

A verification pattern for "are all chunks of file X properly stored?" that avoids the two
expensive LLM operations in the ingestion chain — per-chunk summarization (racochu enrichment)
and embedding creation (bensyne Mnemosyne save). It compares an **expected** chunk set computed
locally with an **actual** stored set read from the MCP side, using only CPU work and cheap reads.

## Why

The only existing probe (`rememberMemory`) is unsafe as a check — a hash miss triggers
save + embedding. Recovery (e.g. `--recover`) needs a state-accurate, non-mutating surface.
The pattern makes full-file verification cheap enough for a maintenance mode.

## Key Details

- **Expected set (racochu, CPU-only):** chunk the file with `skipEnrichment: true` — no Mastra
  `extractMetadata` LLM block, no enhancement pipeline. `metadata.chunkHash` (sha256 of exact
  text) is identical with or without enrichment, so hashes compare with enriched ingests.
- **Actual set (bensyne, zero LLM):** deterministic `file_id = file_{sha256("bank:path")[:32]}`
  computed locally; read `files` + `file_chunks` rows (pure SQLite) via the read-only
  `getFileChunks` tool.
- **Embedding existence:** per-chunk `memory_status` via `mnemosyne_client.get(memory_id)`
  point reads — detects a `file_chunks` row whose Mnemosyne memory is gone (external DB loss,
  restore, consolidation).
- **Repair safety:** re-submission dedups on `chunk_hash` before embedding; `force_reembed`
  guards the stale-hash-index trap (dedup hit whose memory_id is dead).
- **Cost:** healthy file = 1 MCP round-trip + N point reads, zero LLM; damaged file = 1
  whole-file enrichment pass + embeddings for the repair set only.
