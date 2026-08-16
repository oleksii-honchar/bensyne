---
type: adr
id: ADR-0021
title: "Forget After Ingest on File Update"
status: accepted
createdAt: "2026-08-06T18:35:00Z"
updatedAt: "2026-08-06T18:35:00Z"
tags: [file-update, memory-lifecycle, mnemosyne]
supersedes: []
superseded_by: []
see_also: ["adrs/0019-continue-on-forget-failure.adr.md", "concepts/0007-file-memory-tracking.concept.md", "concepts/0005-processing-model.concept.md"]
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0021: Forget After Ingest on File Update

## Context

When a file is updated in a watched directory, the chunker creates new chunks but doesn't clean up old ones. This causes memory bloat over time as old versions of content persist in Mnemosyne indefinitely.

**Evidence:**
- ADR-0010 explicitly states: "When files are deleted or updated in watched directories, we need to update or delete corresponding memories in Mnemosyne"
- The delete flow properly forgets old memories using FileMemoryTracker
- The change flow shared `handleAddOrChange()` with add — no forget logic existed
- Live log evidence: change events add new chunks without forgetting old ones

## Decision

Add forget-after-reingest to the file change flow with separate handlers:

1. **Separate handlers:** `handleAdd()` (ingest only) and `handleChange()` (ingest + forget old)
2. **Extract shared method:** `ingestFile()` shared by both handlers
3. **Forget after new ingest** (not before):

```
File Changed → Get Old Memory IDs → Read File → Chunk → Ingest → Track New → Forget Old → Clear Tracker
```

4. **Per-ID tracker cleanup:** `forgetMemories(filePath, oldMemoryIds)` removes only old IDs, preserving new tracker entries

### Rationale

**Forget after new ingest (not before):**
- **Data safety** — If new ingest fails, old memories still exist
- **User preference** — explicitly requested to avoid data loss on ingest failure
- **Temporary duplicates** — acceptable trade-off for safety

**Separate add and change handlers:**
- Makes the update flow explicit and maintainable
- Different semantics: add = ingest only, change = ingest + forget old
- Easier to reason about behavior

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Forget before new ingest | Clean state | Data loss if new ingest fails | Risk of data loss |
| Share handlers with conditional logic | Less code | Harder to understand, implicit behavior | Maintainability |
| Don't forget old memories | Simple | Violates ADR-0010, memory bloat | Long-term reliability |

## Consequences

- **Positive:** Reliable memory cleanup on file updates, explicit handler semantics
- **Negative:** Additional latency on file changes (forget calls after ingest)
- **Mitigation:** Forget calls are fast, existing debounce handles rapid changes
