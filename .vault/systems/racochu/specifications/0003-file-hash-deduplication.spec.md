---
type: specification
title: "File Hash Deduplication for Cross-Device Sync"
kind: feature
status: completed
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [deduplication, file-hash, cross-device, sync]
owner: ""
target: null
see_also:
  - "adrs/0021-file-hash-deduplication-metadata.adr.md"
  - "adrs/0022-native-machine-id-hardware-detection.adr.md"
  - "adrs/0023-filetracker-schema-extension.adr.md"
  - "concepts/0013-file-hash-deduplication.concept.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Specification: File Hash Deduplication for Cross-Device Sync

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

## Behaviors

- File-based memory with matching fileHash → `{"status": "deduplicated", "memory_id": "existing_id"}`
- File-based memory with new fileHash → stored normally, hash indexed
- Pure memory (no fileHash in metadata) → bypasses dedup entirely, stored normally
- Hash computation failure → log warning, continue pipeline without hash
- Hardware ID detection failure → log warning, continue pipeline without hardwareId
- Hash index lookup/store failure → log warning, continue pipeline

## Risks

- **Risk:** File updates on same device produce new hash → duplicate memories — **Mitigation:** Client-side update handling (forget old, create new) in handleChange flow
- **Risk:** Hash collisions — **Mitigation:** SHA-256 collision probability is negligible (2^-128)

## Milestones

- 2026-08-07: Feature implemented, 797/797 tests passing, all spec requirements met
