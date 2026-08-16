---
type: memory
title: "handleChange: Per-ID forgetMemories Instead of deleteByFilePath"
createdAt: "2026-08-07T18:50:00Z"
updatedAt: "2026-08-07T18:50:00Z"
tags: [bugfix, file-tracking, mnemosyne]
see_also: ["adrs/0020-no-tracker-api-changes.adr.md", "concepts/0007-file-memory-tracking.concept.md"]
---

# Memory: handleChange Per-ID forgetMemories Bug Fix

## Fact

In `ProcessFileUseCase.handleChange()`, tracker cleanup uses `forgetMemories(filePath, oldMemoryIds)` (per-ID removal) instead of `deleteByFilePath(filePath)` (full entry deletion).

## Context

The original implementation used `deleteByFilePath` after forgetting old memories. But `deleteByFilePath` wipes the entire tracker entry — including the new memory IDs that were just added during the ingest step. This caused tracker entries to be lost after every file update.

The fix uses `forgetMemories(filePath, oldMemoryIds)` which calls the aggregate's `forgetMany()` method, removing only the specified old IDs from the `memoryIds` array while preserving new entries.

## Impact

Without this fix, every file update would lose its tracker mapping — the file→memory relationship would be broken after a single change event. Subsequent updates would not know which memories to forget, causing memory bloat. The E2E test for file update flow (`src/e2e/file-update-flow/file-update-flow.test.ts`) catches this regression.
