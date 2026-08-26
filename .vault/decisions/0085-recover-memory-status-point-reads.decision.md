---
type: decision
id: DEC-0086
system: bensyne-mcp
title: "Embedding-Existence Detection in getFileChunks via Mnemosyne Point Reads"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, verification, memory-status, mnemosyne, embedding]
supersedes: []
superseded_by: []
see_also:
  - decisions/0079-recover-getfilechunks-readonly-tool.decision.md
  - decisions/0087-recover-force-reembed.decision.md
  - concepts/0002-memory-domain.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0086: Embedding-Existence Detection in getFileChunks via Mnemosyne Point Reads

## Context

A `file_chunks` row can exist while its actual Mnemosyne memory/embedding is gone (external DB
loss/restore, consolidation, crash between save and materialize). The projection check alone
cannot detect this — "chunks properly stored" must include "memory actually exists". The cheap
primitive is `MnemosyneClient.get(memory_id)` — a point read by id, no embedding, `None` when
missing.

## Decision

`getFileChunks` reports per-chunk `memory_status: "present" | "missing"` by running
`mnemosyne_client.get(memory_id)` for each stored chunk, server-side, within the single MCP call.
Recover treats `memory_status: "missing"` as part of the repair set. Cost: 1 MCP round-trip + N
point reads per file — zero LLM, zero embedding.

## Alternatives Considered

- Batch `getMemoryStatuses(memory_ids)` tool — rejected: more round-trips; the file-scoped tool
  already has the memory ids.
- Bank-level `getMemoryStats` — rejected: not per-file, cannot locate the lost `chunk_index`.
- Skip embedding check (projection only) — rejected: fails the "properly stored" requirement.

## Consequences

- `getFileChunks` is no longer a pure file-layer read; it touches Mnemosyne with N cheap gets.
- Verification per file becomes O(chunks) point reads — bounded, accepted for a maintenance mode.
