---
type: concept
system: shared
title: "Dual-Hash Deduplication"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-17T11:32:38Z"
tags: [deduplication, dual-hash, chunk-hash, file-hash, cross-device]
see_also:
  - decisions/0048-dual-hash-wire-contract.decision.md
  - decisions/0039-file-hash-deduplication-metadata.decision.md
  - specifications/0005-file-hash-deduplication.spec.md
  - concepts/0001-hash-index.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: Dual-Hash Deduplication

## What

Dual-hash deduplication prevents duplicate memories when the same file is ingested from multiple devices. Two first-class hashes travel in `rememberMemory` metadata (contract v1, snake_case — DEC-0048): `chunk_hash` — SHA-256 of the chunk text exactly as sent in `content`, the per-memory dedup key; `file_hash` — SHA-256 of the whole source file, file identity + re-ingest rebuild trigger. There is no top-level hash argument on the wire.

## Why

When a vault is synced across multiple devices (e.g., Mac mini, MacBook Pro), the same file has different absolute paths per device. Without deduplication, re-ingestion creates duplicate memories. Identical file ⇒ identical chunk texts ⇒ identical `chunk_hash` values ⇒ device-2 chunks dedup against device-1 memories — the original cross-device goal (DEC-0039), preserved and strengthened from per-file to per-chunk granularity.

## Key Details

- **chunk_hash producer:** racochu `ChunkContentUseCase` — SHA-256 of the chunk text as sent (non-fatal: failure logs + omits, mirroring the fileHash policy)
- **file_hash producer:** racochu `FileHasherService` at process-file time (unchanged)
- **Wire keys:** `metadata.chunk_hash` / `metadata.file_hash` (snake_case — D12). Racochu-internal camelCase keys (`fileHash`, `chunkHash`) are pre-wire domain data; the DTO (`BensyneRememberDto`) is the translation boundary
- **Dedup index:** per-bank SQLite `data/{memory_bank}/hash_index.db`, `chunk_hash → memory_id` ([[0001-hash-index]]). Hit → `{"status": "deduplicated", "memory_id": …}` **and materialization still runs** with the existing memory_id (idempotent upserts link the shared memory under the new file — identical chunk content across files keeps every file's projection complete)
- **Dedup bypass:** `chunk_hash` absent ⇒ pure memories / legacy producers bypass dedup entirely
- **file_hash absent:** rebuild branch never fires (D5, unchanged)
- **Retrieval surface (D15):** `fetchFile` chunk entries carry `chunk_hash` (null for legacy rows), file block carries `file_hash`; `recallMemory`/`searchFiles` `file_enrichment` carries both; `file_chunks.content_hash` (V3 column) is populated at materialization — no migration
- **Hardware ID:** detected via `native-machine-id`, stored in `FileTracker.hardwareId` for audit (unchanged)
- **Forget cleanup:** when a memory is forgotten via `forgetMemory`, its hash_index entry is removed (keyed by memory_id)
