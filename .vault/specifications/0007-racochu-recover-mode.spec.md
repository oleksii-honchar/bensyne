---
type: specification
system: racochu
kind: feature
title: "Racochu CLI recover Mode — Zero-LLM Chunk Recovery"
status: completed
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
owner: ""
target: ""
see_also:
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - decisions/0080-recover-skipenrichment-chunking.decision.md
  - decisions/0081-recover-exiting-cli-mode.decision.md
  - decisions/0082-recover-additive-recovery-change-semantics.decision.md
  - decisions/0083-recover-filetracker-known-files.decision.md
  - decisions/0084-recover-hash-gate-chunk-set-check.decision.md
  - decisions/0085-recover-memory-status-point-reads.decision.md
  - decisions/0086-recover-force-reembed.decision.md
  - concepts/0025-cheap-chunk-verification.concept.md
  - runbooks/0006-racochu-recover-mode.runbook.md
---

# Specification: Racochu CLI recover Mode — Zero-LLM Chunk Recovery

## Goal

Add a `--recover` CLI mode that repairs chunk-level gaps for files already tracked in the local
DB: iterate `FileTracker` rows only, compute the expected chunk set locally (chunking **without
enrichment**, CPU-only), read the actual stored set from bensyne via the new read-only
`getFileChunks` tool (1 SQLite read + N Mnemosyne point reads, no embedding), and re-ingest only
missing chunks through the regular pipeline (enrichment when enabled + embedding). Missing
embedding is repaired safely via the `force_reembed` flag (stale-hash-index guard). Mode exits
after the pass (no watch).

## Cost Profile

- Healthy files: zero LLM calls (local chunking + one cheap MCP read with N point reads).
- Damaged files: 1 whole-file enrichment pass + embeddings for the repair set only.

## Phases

1. bensyne-mcp `getFileChunks` (read-only tool + `memory_status` point reads)
2. racochu `BensyneClient.getFileChunks()` + `remember(chunk, { forceReembed })`
3. enrichment-free chunking variant (`ChunkContentUseCase.skipEnrichment`; Mastra 5th-param override)
4. `RecoverService` (decision table) + `FileTrackerRepository.findTrackedBySourceId(sourceId?)`
5. bensyne-mcp `rememberMemory` `force_reembed` repair flag
6. CLI wiring (`--recover`, exit-after-pass, `--source`, `--dry-run`)
7. e2e + docs

## Behaviors

- Decision table per file: missing-on-disk → skip+warn; FILE_NOT_FOUND → full re-ingest (add);
  changed hash → full re-ingest (change semantics); legacy null hash → skip gate; healthy → skip;
  missing index / `memory_status=missing` → repair set submit with `forceReembed: true`.
- Serialization: direct `IngestChunkUseCase` submit wrapped in `processingQueue.addToQueue` from
  the top-level loop (never from inside a queued task — deadlock-by-design).

## Risks

- Config drift ⇒ false "missing" for healthy files (MEDIUM) — dedup protects re-submission.
- Stale hash-index dedup trap (HIGH without fix) — mitigated by `force_reembed` guard.
- `getFileChunks` not deployed (MEDIUM) — spec says recover aborts with clear message;
  ⚠️ implementation logs per-file errors but exits 0 (review medium finding, tracked follow-up).
