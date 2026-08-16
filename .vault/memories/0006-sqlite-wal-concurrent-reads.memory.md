---
type: memory
system: bensyne-mcp
title: "HashIndex Uses SQLite WAL Mode for Concurrent Reads"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-12T16:58:00Z"
tags: [sqlite, wal, hash-index, concurrency]
see_also:
  - concepts/0001-hash-index.concept.md
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: HashIndex Uses SQLite WAL Mode for Concurrent Reads

## Fact

The `HashIndexService` in Bensyne uses SQLite's WAL (Write-Ahead Logging) journal mode, enabling concurrent reads while writes are serialized via a threading lock.

## Context

The `rememberMemory` handler opens a hash-index connection for each incoming file-based memory. With multiple concurrent requests, WAL mode allows readers to proceed without blocking on writers. The service is SQLAlchemy-backed (`HashIndexService` in `src/infrastructure/mcp/hash_index_service.py`) with per-operation locking.

## Impact

Without WAL mode, concurrent read/write operations could cause "database is locked" errors. WAL mode is set via `PRAGMA journal_mode=WAL` on the SQLAlchemy engine.
