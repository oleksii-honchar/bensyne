---
type: concept
system: racochu
title: "File→Memory Tracking"
createdAt: "2026-08-01T12:00:00Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [file-tracking, mnemosyne, prisma, file-hash, hardware-id]
see_also: [decisions/0028-file-memory-tracking-prisma-sqlite.decision.md, decisions/0038-no-tracker-api-changes.decision.md, decisions/0041-filetracker-schema-extension.decision.md, concepts/0012-processing-model.concept.md, concepts/0020-file-hash-deduplication.concept.md, memories/0013-change-handler-per-id-forget-memory.memory.md, decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md]
---

# Concept: File→Memory Tracking

## What

File→Memory tracking maintains a local Prisma SQLite database mapping watched file paths to Mnemosyne memory IDs. This enables reliable memory cleanup when files are deleted or updated.

## Why

Without tracking, memories persist indefinitely even after source files are deleted. Semantic recall-based cleanup is unreliable — it may miss memories or delete wrong ones. Direct memory ID lookup guarantees correct cleanup.

## Key Details

**Schema:**
- `FileTracker` — One row per file (filePath unique)
- `FileMemoryTracker` — One row per memory ID linked to a file (FK to FileTracker)

**Flow on file creation:**
1. `IngestChunkUseCase` calls `MnemosyneClient.remember(chunk)` → returns `{memory_id}`
2. `FileMemoryTrackerService.trackMemory(filePath, memoryId)` creates/updates tracker

**Flow on file update:**
1. `ProcessFileUseCase.handleChange()` calls `tracker.getMemoryIds(filePath)` to get old memory IDs
2. `ingestFile()` reads, chunks, enhances, and ingests new content — new memory IDs tracked via `trackMemory()`
3. `forgetOldMemoriesByIds()` calls `MnemosyneClient.forget(memoryId, memoryBank)` for each old ID (continue on failure)
4. `tracker.forgetMemories(filePath, oldMemoryIds)` removes only old IDs from tracker, preserving new entries (per-ID cleanup, not `deleteByFilePath` — see memory 0006)

**Flow on file deletion:**
1. `ProcessFileUseCase.handleDelete()` calls `tracker.getMemoryIds(filePath)`
2. For each memory ID, calls `MnemosyneClient.forget(memoryId, namespace)`
3. Removes tracker entry via `deleteByFilePath(filePath)`

**Storage:** Local SQLite at `data/file_memory.db`, managed via Prisma.

**Tracker operations:**
- `trackMemory(filePath, memoryId)` — adds memory ID to file's tracker (aggregate `remember()`)
- `forgetMemory(filePath, memoryId)` — removes single memory ID (aggregate `forget()`)
- `forgetMemories(filePath, memoryIds[])` — removes multiple memory IDs (aggregate `forgetMany()`) — used by handleChange to preserve new entries
- `deleteByFilePath(filePath)` — removes entire tracker row — used only by handleDelete
- `updateFileTrackerHash(filePath, fileHash, hardwareId)` — updates fileHash/hardwareId on FileTracker parent record after upsert

**Deduplication support (fileHash + hardwareId):**
- `FileTracker.fileHash` — nullable String, SHA-256 hash of file content, indexed for hash lookups
- `FileTracker.hardwareId` — nullable String, device ID from `native-machine-id`, indexed for audit
- Populated by `IngestChunkUseCase` → `FileMemoryTrackerService.trackMemory()` → `repository.updateFileTrackerHash()`
- Enables local dedup checks before calling Mnemosyne (see `concepts/0020-file-hash-deduplication.concept.md`)

---

### Update 2026-11-01 — Final-decision invariant + terminal-skip rows (DEC-0119)

`FileTracker` semantics tightened to a **final-decision store** (aggregate docstring invariant):

> *A FileTracker row means: racochu has seen this exact content hash and reached a final decision
> about it — ingested (memories tracked, `skipReason` null) or terminally skipped (`skipReason`
> set, zero memories).*

- **New nullable column `FileTracker.skipReason`** (`'content-filtered' | 'empty-content' |
  'zero-chunks'`; enum-style const `FILE_TRACKER_SKIP_REASON`, pattern per DEC-0041). Rows with
  `skipReason` set carry **zero** `FileMemoryTracker` children by design.
- **Self-clearing:** no status machine — a content change makes the hash differ and normal
  processing re-evaluates; a successful ingest clears `skipReason` alongside
  `updateFileTrackerHash`.
- **Gate-facing reads** (on the repository `FileMemoryTrackerService` owns):
  `findHashAndSkipReasonByFilePath(filePath)` → single indexed read; service wrappers
  `getIngestGateState(filePath)` (fail-open: DB error ⇒ caller treats as "not gated") and
  `recordTerminalSkip(...)` (non-fatal write, try/catch-warn).
- **Consumer note:** the ~+250 expected zero-memory rows were audited safe for recover (deterministic
  cheap re-skip via step-4 FILE_NOT_FOUND + forceIngest), re-embed (no chunk work), TTL/mass-forget-guard
  (row-count based; zero-memory forget is a bank no-op) — DEC-0119 consequences.
