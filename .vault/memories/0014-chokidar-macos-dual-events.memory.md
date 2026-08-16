---
type: memory
system: racochu
title: "Chokidar Dual Events on macOS — Processing Set Dedup"
createdAt: "2026-08-07T18:50:00Z"
updatedAt: "2026-08-07T18:50:00Z"
tags: [bugfix, chokidar, macos, file-watching]
see_also: [concepts/0012-processing-model.concept.md, decisions/0036-forget-after-ingest-on-file-update.decision.md]
---

# Memory: Chokidar Dual Events on macOS

## Fact

macOS chokidar fires duplicate events for the same file change (e.g., two `change` events). ProcessFileUseCase uses an in-memory `processing` Set to skip duplicate events for the same file path.

## Context

Live testing revealed that a single file edit on macOS triggered two `change` events from chokidar. Without dedup, both events would go through the full forget-ingest-reingest cycle — wasting API calls and potentially causing race conditions with the tracker.

The fix adds a `processing: Set<string>` in `ProcessFileUseCase.executeInternal()`. When an event arrives, it checks if the file is already in the set — if yes, it skips processing. The set entry is cleared in a `finally` block after queue processing completes.

```typescript
// Skip if already processing this file
if (this.processing.has(params.filePath)) {
  this.logger.debug(`Skipping duplicate event: path="${params.filePath}"`);
  return Result.ok(undefined as unknown as void);
}
this.processing.add(params.filePath);
// ... queue processing ...
finally {
  this.processing.delete(params.filePath);
}
```

## Impact

Without this fix, every file change on macOS would be processed twice — doubling API calls to Mnemosyne and potentially corrupting the tracker state (forgetMemories called on already-removed IDs). Verified with live chunker testing: change 17→17 memories (correct), vs. without fix it would be 17→34.
