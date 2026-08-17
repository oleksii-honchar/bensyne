---
type: specification
system: racochu
title: "Dual-Hash Deduplication for Cross-Device Sync"
kind: feature
status: completed
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-17T11:32:38Z"
tags: [deduplication, dual-hash, chunk-hash, file-hash, cross-device, sync]
owner: ""
target: null
see_also:
  - decisions/0039-file-hash-deduplication-metadata.decision.md
  - decisions/0040-native-machine-id-hardware-detection.decision.md
  - decisions/0041-filetracker-schema-extension.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - concepts/0020-file-hash-deduplication.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Specification: Dual-Hash Deduplication for Cross-Device Sync

## Goal

Prevent duplicate memories when the same Obsidian vault is synced across multiple devices. Same content with different absolute paths should resolve to a single memory.

## Phases

### Phase 1 — Hash Computation and Metadata (RAG Content Chunker)

- [x] FileHasherService computes SHA-256 via Node.js `crypto.createHash('sha256')`
- [x] HardwareIdDetectorService detects hardware ID via `native-machine-id`
- [x] ProcessFileUseCase injects fileHash and hardwareId into chunk metadata
- [x] ChunkContentUseCase merges fileHash/hardwareId into chunk metadata before enhancement

### Phase 2 — Deduplication (Bensyne)

- [x] HashIndex: SQLite WAL-mode per memory bank at `data/{memory_bank}/hash_index.db`
- [x] memory_remember handler: extract fileHash → lookup HashIndex → return "deduplicated" if found
- [x] memory_remember handler: index hash after successful memory creation
- [x] memory_forget handler: clean up HashIndex entry (non-fatal)

### Phase 3 — FileTracker Schema Extension (RAG Content Chunker)

- [x] FileTracker schema extended with `fileHash` and `hardwareId` nullable String fields
- [x] Prisma indexes on both fields
- [x] `updateFileTrackerHash` repository method for post-upsert persistence

### Phase 4 — Dual-Hash Wire Contract (2026-08-17, DEC-0048)

- [x] Wire keys: `metadata.chunk_hash` (sha256 of chunk text as sent — per-memory dedup) + `metadata.file_hash` (sha256 of whole file — rebuild trigger, D5 unchanged); NO top-level `hash` argument
- [x] Racochu `ChunkContentUseCase` computes `chunkHash`; DTO drops top-level `hash`, emits `metadata.chunk_hash`
- [x] Bensyne `HashIndex` re-keyed `file_hash → chunk_hash` (one-time legacy-table drop, no row copy); dedup-hit STILL materializes with the existing memory_id (idempotent)
- [x] Retrieval surfaces both hashes: fetchFile chunk entries `chunk_hash` + file block `file_hash`; recallMemory/searchFiles `file_enrichment` both
- [x] Contract parity fixtures updated (both apps, byte-identical); e2e `file-hash-dedup/first-device` + `enrichment-verification` PASS

## Behaviors

- File-based memory with matching `chunk_hash` → `{"status": "deduplicated", "memory_id": "existing_id"}` AND materialization still runs with the existing id (idempotent)
- File-based memory with new `chunk_hash` → stored normally, chunk_hash indexed
- Pure memory (no `chunk_hash` in metadata) → bypasses dedup entirely, stored normally
- Legacy rows without stored `content_hash` → retrieval surfaces `chunk_hash: null` (no backfill)
- Hash computation failure → log warning, continue pipeline without hash
- Hardware ID detection failure → log warning, continue pipeline without hardwareId
- Hash index lookup/store failure → log warning, continue pipeline

## Risks

- **Risk:** File updates on same device produce new hash → duplicate memories — **Mitigation:** Client-side update handling (forget old, create new) in handleChange flow
- **Risk:** Hash collisions — **Mitigation:** SHA-256 collision probability is negligible (2^-128)

## Milestones

- 2026-08-07: Feature implemented, 797/797 tests passing, all spec requirements met
- 2026-08-17: Dual-hash wire contract delivered (DEC-0048); bensyne 1454/0, racochu 818/0; both previously-blocked e2e suites PASS
