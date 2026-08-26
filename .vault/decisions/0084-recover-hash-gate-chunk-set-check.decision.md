---
type: decision
id: DEC-0085
system: racochu
title: "Hash Equality Is the Change Gate; Chunk-Set Comparison Is the Completeness Check"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-26T07:18:26Z"
tags: [recover, hash, change-gate, completeness, verification]
supersedes: []
superseded_by: []
see_also:
  - decisions/0048-dual-hash-wire-contract.decision.md
  - decisions/0039-file-hash-deduplication-metadata.decision.md
  - concepts/0020-file-hash-deduplication.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0085: Hash Equality Is the Change Gate; Chunk-Set Comparison Is the Completeness Check

## Context

Two comparisons exist in the decision table: (a) has the file changed since ingest? (b) are all
chunks stored? The wire already defines the signals: `file_hash` (whole-file, DEC-0048) and
`chunk_hash` (per-chunk dedup key).

## Decision

Recover uses current computed `fileHash` vs `FileTracker.fileHash` as the change gate (free,
local, no MCP call); uses `content_hash` per stored `chunk_index` from `getFileChunks` vs
locally computed `metadata.chunkHash` as the completeness check. A null `FileTracker.fileHash`
(legacy rows) skips the change gate and falls back to chunk-set comparison only.

## Alternatives Considered

- Use bensyne `file_hash` from `getFileChunks` as the gate — equivalent but requires the MCP
  call first; local gate is strictly cheaper and independent.

## Consequences

- ⚠️ Wording vs implementation (review low finding): `contentHash` from `getFileChunks` is parsed
  but the repair-set computation uses `chunkIndex` presence + `memoryStatus` only — a stored
  chunk with wrong content at a present index is treated as healthy. Matches the spec §4.2
  decision table; documented for the developer to align wording or compare hashes.
