---
type: concept
system: bensyne-mcp
title: "HashIndex"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [hash-index, deduplication, sqlite]
see_also:
  - decisions/0008-sqlite-hash-index.decision.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Concept: HashIndex

## What

HashIndex is a SQLite-backed index in Bensyne that maps file hashes to memory IDs, enabling fast exact-match deduplication before creating new memories.

## Why

When the same file is ingested from multiple devices, its SHA-256 hash is identical regardless of file path. The HashIndex checks for existing hashes before creating new memories, returning a "deduplicated" status if a match is found.

## Key Details

- **Location:** `data/{memory_bank}/hash_index.db` — one database per memory bank
- **Mode:** WAL mode for concurrent reads
- **Implementation:** `HashIndexService` in `src/infrastructure/mcp/hash_index_service.py` — SQLAlchemy ORM, thread-safe via per-operation `threading.Lock`, returns `Result[T]`
- **Operations:**
  - `lookup(file_hash)` → returns `memory_id` or `None`
  - `store(file_hash, memory_id)` → get-or-update (add new row or update `memory_id` in place)
  - `remove(memory_id)` → deletes entry on `memory_forget`, returns the `file_hash`
- **Thread-safe:** Per-operation locking via `threading.Lock`
- **Non-fatal:** HashIndex errors log a warning; the remember/forget pipeline continues
