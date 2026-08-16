---
type: decision
id: DEC-0038
system: racochu
title: "No Tracker API Changes Needed for File Update Flow"
status: accepted
createdAt: "2026-08-06T18:35:00Z"
updatedAt: "2026-08-06T18:35:00Z"
tags: [file-tracking, api-design, mnemosyne]
supersedes: []
superseded_by: []
see_also: [decisions/0036-forget-after-ingest-on-file-update.decision.md, concepts/0014-file-memory-tracking.concept.md]
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# DEC-0038: No Tracker API Changes Needed for File Update Flow

## Context

The file update flow needs to query old memory IDs, forget memories, and clear the tracker. The question was whether the existing FileMemoryTrackerService API is sufficient.

## Decision

**Use existing FileMemoryTrackerService API — no changes needed.** The existing methods cover all requirements:

- `getMemoryIds(filePath)` — query old memories before forget
- `forgetMemories(filePath, oldMemoryIds)` — per-ID removal of old entries, preserving new tracker data
- `trackMemory(filePath, memoryId, ...)` — add new memory IDs during ingest

**Rationale:**
1. Delete flow already uses this pattern successfully
2. No new use cases that existing API doesn't cover
3. Minimizes change surface

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Add `forgetAndClear(filePath)` | Single call | Mixes concerns, tracker shouldn't know about Mnemosyne | Separation of concerns |
| Add `getAndClear(filePath)` | Atomic operation | Atomicity not needed, two calls sufficient | Not worth the complexity |

## Consequences

- **Positive:** Minimal changes, uses proven patterns
- **Negative:** Two separate calls (get IDs, then clear)
- **Mitigation:** Clear tracker after forget — order is explicit
