---
type: concept
title: "File Hash Deduplication"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [deduplication, file-hash, cross-device]
see_also:
  - "adrs/0021-file-hash-deduplication-metadata.adr.md"
  - "specifications/0003-file-hash-deduplication.spec.md"
  - "concepts/0001-hash-index.concept.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: File Hash Deduplication

## What

File hash deduplication prevents duplicate memories when the same file is ingested from multiple devices. A SHA-256 hash of file content is computed in RAG Content Chunker, included in the `fileHash` metadata field, and checked against a HashIndex in Bensyne before creating a new memory.

## Why

When an Obsidian vault is synced across multiple devices (e.g., Mac mini, MacBook Pro), the same file has different absolute paths on each device. Without deduplication, ingesting the same file from two devices creates duplicate memories — same content, different entries.

## Key Details

- **Hash algorithm:** SHA-256 via Node.js `crypto.createHash('sha256')` in `FileHasherService`
- **Hash index:** SQLite WAL-mode database at `data/{memory_bank}/hash_index.db`, mapping `file_hash → memory_id`
- **Dedup flow:** RAG Content Chunker computes hash → includes in `memory_remember` metadata → Bensyne checks HashIndex → returns "deduplicated" if found
- **Pure memories:** Memories without a `fileHash` in metadata bypass dedup entirely
- **Hardware ID:** Detected via `native-machine-id` npm module, stored in `FileTracker.hardwareId` for audit
- **Non-fatal failures:** Hash or hardware ID computation failures log a warning and continue the pipeline
- **Forget cleanup:** When a memory is forgotten via `memory_forget`, its HashIndex entry is removed
