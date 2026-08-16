---
type: adr
id: ADR-0022
title: "Continue on Forget Failure — Don't Block Re-ingestion"
status: accepted
createdAt: "2026-08-06T18:35:00Z"
updatedAt: "2026-08-06T18:35:00Z"
tags: [error-handling, memory-lifecycle, resilience]
supersedes: []
superseded_by: []
see_also: ["adrs/0018-forget-after-ingest-on-file-update.adr.md"]
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0022: Continue on Forget Failure — Don't Block Re-ingestion

## Context

When forgetting old memories before re-ingestion, some forget calls may fail due to network issues, Mnemosyne errors, or permission problems.

## Decision

**Continue with re-ingestion even if some forget calls fail.** Log warnings but don't block the new content ingestion. Implemented via `forgetOldMemoriesByIds()` which iterates over each memory ID with try/catch, counts failures, and returns `Result.ko(errors)` only for logging — the caller (handleChange) treats it as non-fatal.

**Rationale:**
1. **Data safety** — New content is always ingested
2. **Operational resilience** — Transient failures don't block updates
3. **Idempotency** — Failed forgets retry on next change event

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Fail on any forget error | Clean state | New content blocked by old content issues | Overly strict |
| Fail on all forget errors | Partial cleanup | Still blocks new content unnecessarily | Not worth the penalty |
| Skip re-ingestion if forget partially fails | Honest error handling | Penalizes user for cleanup failure | Bad user experience |

## Consequences

- **Positive:** System remains operational even with forget failures
- **Negative:** Some old memories may persist temporarily
- **Mitigation:** Old memories will be forgotten on next update or delete
