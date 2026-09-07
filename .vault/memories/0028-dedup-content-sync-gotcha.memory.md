---
type: memory
system: bensyne-mcp
title: "Hash-Dedup Hits Keep Stale Memory Content"
createdAt: "2026-09-07T13:05:59Z"
updatedAt: "2026-09-07T13:05:59Z"
tags: [deduplication, content-sync, bensyne-mcp, gotcha]
see_also:
  - decisions/0107-dedup-content-sync-fix.decision.md
  - concepts/0020-file-hash-deduplication.concept.md
  - decisions/0086-recover-force-reembed.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: Hash-Dedup Hits Keep Stale Memory Content

## Fact

On a chunk-hash dedup hit, `RememberMemoryUseCase` returns the existing
`memory_id` without refreshing the memory's `content` field. Re-ingesting a
file whose chunk hash already exists can therefore leave the memory with
empty/stale content even though the file on disk is fine. This manifested as
`getPersonaEntryNode` returning `text: ""` for the icm-operator entry node.

## Context

Discovered 2026-09-07 during the icm-operator empty-text investigation. The
hash index ([[concepts/0020-file-hash-deduplication]]) prevents duplicate
embeddings, but the memory `content` is a separate cache that dedup never
touched. ADR-11 ([[decisions/0107-dedup-content-sync-fix]]) fixes this by
calling `memory_repository.update(content=...)` on every dedup hit; racochu
recover now always re-ingests (`repairSet = expectedChunks`) so the sync path
always runs.

## Impact

Without the fix, re-ingestion could never repair an empty/stale memory — same
chunk hash → same memory_id → same empty content. Keeping content in sync on
dedup hits makes re-ingestion a reliable repair path, complementing the
`force_reembed` stale-hit repair ([[decisions/0086-recover-force-reembed]]).