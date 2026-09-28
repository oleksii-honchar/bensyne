---
type: decision
id: DEC-0112
system: bensyne-mcp
title: "Use Client-Side `_remember_episodic()` Instead of Library's `remember_episodic()`"
status: accepted
createdAt: "2026-09-28T18:47:00Z"
updatedAt: "2026-09-28T18:47:00Z"
tags: [episodic-memory, remember, mnemosyne, bensyne-mcp, ttl]
supersedes: []
superseded_by: []
see_also:
  - decisions/0109-episodic-memory-tier-migration.decision.md
  - decisions/0113-file-chunks-reingest-index-fix.decision.md
  - decisions/0114-verify-source-consistency-beam.decision.md
---

# DEC-0112: Use Client-Side `_remember_episodic()` Instead of Library's `remember_episodic()`

## Context

ADR-13 (DEC-0110) established that bensyne-managed memories should be inserted directly into the `episodic_memory` table, bypassing `working_memory`. The original implementation used raw SQL INSERT statements in `mnemosyne_client.py`. During investigation of the episodic memory insertion approach, it was discovered that the Mnemosyne library already provides a `remember_episodic()` method for direct episodic inserts.

The question arose whether bensyne should switch from raw SQL to the library's `remember_episodic()` method.

## Decision

Replace the raw SQL INSERT in `save()` and `remember()` methods with a client-side `_remember_episodic()` method that wraps the library's API while adding Bensyne-specific features (primarily `valid_until` TTL support). This method:
- Uses the library's transaction handling
- Generates embeddings properly
- Adds `valid_until` field support (not available in library's `remember_episodic()`)
- Adds `metadata_json` and `veracity` fields

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Use library's `remember()` API | Standard approach | Inserts into `working_memory` first, defeating ADR-13's purpose (avoiding trim) | Would break the episodic-tier design |
| Use library's `remember_episodic()` directly | Library encapsulation | Lacks `valid_until` support; less flexible | Missing TTL feature needed for agent-session memories |
| Keep raw SQL | Simple, proven | Duplicates library functionality; less robust | Client-side method provides better encapsulation |
| Call `consolidate_to_episodic()` | Uses library API | Requires fabricating working memory row first | Unnecessarily complex |

## Consequences

- **Positive:** Better encapsulation of library API; `valid_until` (TTL) support for agent-session memories; `metadata_json` and `veracity` fields available; transaction safety preserved; future library improvements to `remember_episodic()` are automatically available.
- **Negative:** Slightly more complexity than raw SQL; requires maintaining the client-side wrapper method.
- **Neutral:** Design intent of ADR-13 (direct episodic insert, bypass working_memory) is preserved.

## Verification

- Unit tests: `test_mnemosyne_client_remember_episodic.py` (6 tests), `test_mnemosyne_client_save_episodic.py` (8 tests) — all passing
- Integration: 50 tests total across remember/save/reingest verification — all passing
- Manual verification against `episodic_memory` table confirms INSERT works correctly with TTL policy