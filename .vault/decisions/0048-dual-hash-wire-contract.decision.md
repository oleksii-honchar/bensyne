---
type: decision
id: DEC-0048
system: shared
title: "Dual-Hash Wire Contract — snake_case Naming, chunk_hash + file_hash in metadata"
status: accepted
createdAt: "2026-08-17T11:32:38Z"
updatedAt: "2026-08-17T11:32:38Z"
tags: [deduplication, dual-hash, chunk-hash, file-hash, wire-contract, snake-case]
supersedes: []
superseded_by: []
see_also:
  - concepts/0020-file-hash-deduplication.concept.md
  - concepts/0001-hash-index.concept.md
  - specifications/0005-file-hash-deduplication.spec.md
  - decisions/0039-file-hash-deduplication-metadata.decision.md
---

# DEC-0048: Dual-Hash Wire Contract — snake_case Naming, chunk_hash + file_hash in metadata

## Context

The cornerstone delivery left a three-way hash divergence on the racochu → bensyne wire: (1) the contract doc defined a top-level remember `hash` that the `rememberMemory` tool signature never declared — FastMCP's strict schema rejected every cross-app remember call (recall 0); (2) the racochu DTO sent the FILE hash as that top-level `hash` while bensyne's dedup reader looked for camelCase `metadata.fileHash` the DTO no longer emitted — dedup starved. Wire naming was also mixed: all 11 tool params and the whole contract v1 metadata table are snake_case, tool names are camelCase, and one stale camelCase reader (`fileHash`) remained.

## Decision

**D12 — snake_case canonical on the wire.** All MCP tool params and contract metadata keys use snake_case, including the hash fields (`chunk_hash`, `file_hash`). Tool *names* stay camelCase (D1 — names are identifiers, a separate namespace from data keys). Racochu-internal chunk metadata stays camelCase pre-wire; the DTO is the translation boundary. Net renames on the shipped surface = zero.

**D13 — Two first-class hashes in `metadata`; no top-level hash.** `rememberMemory.metadata` carries `chunk_hash` (sha256 of the chunk text exactly as sent in `content`; per-memory dedup key; produced by racochu `ChunkContentUseCase`) and `file_hash` (sha256 of the whole source file; file identity + re-ingest rebuild trigger, D5 unchanged; produced by `FileHasherService`). The top-level `hash` argument does not exist on the wire; the tool signature is unchanged; contract version stays 1 (additive optional field).

**D14 — Dedup index re-keyed to `chunk_hash`; dedup-hit still materializes.** `hash_index` (per-bank SQLite) PK column renamed `file_hash → chunk_hash`; the reader is snake_case `metadata["chunk_hash"]` only. One-time legacy migration at connection init: old-shape table dropped without row copy (file-hash values are a different value space — copying would be incorrect); cost is one-time dedup misses (at most one duplicate memory per re-ingested chunk, accepted). On a dedup hit, `rememberMemory` returns `{"status": "deduplicated", "memory_id": …}` **after** running materialization with the existing `memory_id` (idempotent upserts link the shared memory under the new file — fixes projection loss for identical chunk content across files).

**D15 — Retrieval surfaces both hashes.** No migration: materialization sets `file_chunks.content_hash = context.chunk_hash` (V3 column). `fetchFile` — chunk entries += `chunk_hash` (null for legacy rows), `include_metadata` file block += `file_hash`; `recallMemory`/`searchFiles` — `file_enrichment` block += `file_hash` + `chunk_hash` (null-tolerant). Pure memories keep `file_enrichment: null` (D7).

## Alternatives Considered

1. **camelCase everywhere** — rejected: renames every param of all 11 tools, the contract table, both model mirrors, fixtures, e2e assertions, and vault docs for zero behavior gain.
2. **Top-level `chunk_hash` param (or renamed `hash` param) + `metadata.file_hash`** — rejected: reintroduces a second hash slot with re-drift potential (the shape that broke T9) and splits the payload across two locations.
3. **Single file-hash only (pre-T9 model)** — rejected by user: chunk-level dedup is required; file-hash dedup conflates chunks #2..N of one file.
4. **Composite dedup key `(chunk_hash, file_path)`** — rejected: breaks cross-device dedup (paths differ per device — the original DEC-0039 problem); revisit only if collisions prove frequent.
5. **Recompute chunk hash from stored content at retrieval** — rejected: per-call SHA-256, normalization-drift risk, mnemosyne round-trip dependency; the column exists and is authoritative.
6. **Copy legacy hash_index rows under reinterpretation** — rejected: file-hash values in a chunk-hash-keyed table are silently wrong data.

## Consequences

- One location, explicit names — the T9 ambiguity class (one slot, two candidate semantics) is eliminated.
- Cross-device dedup preserved and strengthened: identical file on two devices ⇒ identical chunk texts ⇒ identical `chunk_hash` ⇒ device-2 dedups against device-1 (original DEC-0039 goal, now per-chunk).
- `FileTracker.fileHash` (racochu Prisma) unchanged; `rememberMemory` signature unchanged (10 params); no file-layer migration (V3 `content_hash` column existed, now populated).
- One-time dedup misses after the index re-key (accepted, LOW — no data loss); legacy `content_hash` NULLs surfaced as `null` on retrieval (S7, documented).
- Supersedes-in-part: DEC-0039 (file-hash-in-metadata dedup → chunk-hash wire contract; cross-device goal preserved).
- Delivered 2026-08-17 (H1–H8): bensyne 1454/0, racochu 818/0, contract parity sha `02c99bb5…`, both previously-blocked e2e suites PASS.
