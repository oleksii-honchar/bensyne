---
type: concept
system: bensyne-mcp
title: "HashIndex"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-17T11:32:38Z"
tags: [hash-index, deduplication, sqlite]
see_also:
  - decisions/0008-sqlite-hash-index.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: HashIndex

## What

HashIndex is a SQLite-backed index in Bensyne that maps chunk hashes to memory IDs (`chunk_hash → memory_id`), enabling fast exact-match deduplication before creating new memories.

## Why

When the same file is ingested from multiple devices, its chunk SHA-256 hash is identical regardless of file path (identical file ⇒ identical chunk texts ⇒ identical `chunk_hash`). The HashIndex checks for existing hashes before creating new memories, returning a "deduplicated" status if a match is found.

## Key Details

- **Location:** `data/{memory_bank}/hash_index.db` — one database per memory bank
- **Mode:** WAL mode for concurrent reads
- **Implementation:** `HashIndexService` in `src/infrastructure/mcp/hash_index_service.py` — SQLAlchemy ORM, thread-safe via per-operation `threading.Lock`, returns `Result[T]`
- **Operations:**
  - `lookup(chunk_hash)` → returns `memory_id` or `None`
  - `store(chunk_hash, memory_id)` → get-or-update (add new row or update `memory_id` in place)
  - `remove(memory_id)` → deletes entry on `forgetMemory`, returns the `chunk_hash`
- **Reader:** snake_case `metadata["chunk_hash"]` only (`extract_chunk_hash` / `has_chunk_hash`) — the stale camelCase `fileHash` reader was removed (DEC-0048/D12)
- **Legacy migration (one-time, at connection init):** if `PRAGMA table_info(hash_index)` shows the old `file_hash` column, the table is recreated with the `chunk_hash` PK and the old one dropped — **no row copy** (legacy rows are file-hash-keyed, a different value space). Effect: one-time dedup misses ⇒ at most one duplicate memory per re-ingested chunk (accepted, no data loss — DEC-0048/D14)
- **Thread-safe:** Per-operation locking via `threading.Lock`
- **Non-fatal:** HashIndex errors log a warning; the remember/forget pipeline continues
