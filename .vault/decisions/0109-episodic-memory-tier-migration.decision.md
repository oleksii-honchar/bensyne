---
type: decision
id: DEC-0110
system: bensyne-mcp
title: "ADR-13: Episodic Memory Tier Migration — Direct INSERT into episodic_memory"
status: accepted
createdAt: "2026-09-26T16:10:13Z"
updatedAt: "2026-09-26T16:10:13Z"
tags: [episodic-memory, working-memory, trim, ttl, migration, mnemosyne, bensyne-mcp]
supersedes: []
superseded_by: []
see_also:
  - concepts/0020-file-hash-deduplication.concept.md
  - memories/0020-mnemosyne-valid-until-soft-expiry.memory.md
---

# ADR-13: Episodic Memory Tier Migration — Direct INSERT into episodic_memory

## Context

Mnemosyne's automatic working memory trim (`_trim_working_memory`) was deleting decision tree node memories that were stored in the `working_memory` table. The trim mechanism deletes `working_memory` rows that are:

1. Older than `WORKING_MEMORY_TTL_HOURS` (default: 168 hours / 7 days)
2. Beyond `WORKING_MEMORY_MAX_ITEMS` (default: 10,000 items)

There's no "permanent" or "pinned" scope option in the Mnemosyne `remember()` API for the bensyne producer. The node memories have no `pinned=1` flag, so they're subject to the automatic trim.

After 7 days (or after 10K items), Mnemosyne deletes them. But bensyne's file layer still has the projection (file_id, file_hash, chunk links), creating the "missing chunk" symptom that manifests as decision tree nodes becoming unavailable.

## Decision

Route all bensyne-managed memories directly into the `episodic_memory` table, bypassing `working_memory` entirely. This approach follows the proven `hindsight` importer pattern in Mnemosyne.

### Key Implementation Details

**Ingest path change:**
```
OLD: Racochu → bensyne rememberMemory() → Mnemosyne remember() → working_memory table
NEW: Racochu → bensyne rememberMemory() → direct INSERT into episodic_memory table
```

**Modified methods** (`apps/bensyne-mcp/src/infrastructure/mnemosyne/mnemosyne_client.py`):
- `save()` — now uses direct `INSERT OR IGNORE INTO episodic_memory` with source-specific TTL
- `remember()` — same direct INSERT pattern
- `forget()` — now uses direct `DELETE FROM episodic_memory WHERE id = ?` with library fallback
- `update()` — now uses direct `UPDATE episodic_memory SET content=?, importance=? WHERE id=?` with library fallback

**Migration script** (`apps/bensyne-mcp/scripts/migrate-working-to-episodic.py`):
- Moves all existing `working_memory` rows to `episodic_memory`
- Idempotent (INSERT OR IGNORE)
- Applies TTL policy during migration

### Source-Specific TTL Policies

| Memory Bank | TTL | Expiry |
|---|---|---|
| `user_<id>` | Infinity | Never |
| `agent-persona_<agent>` (node memories) | Infinity | Never |
| `agent-persona_<agent>` (occasional memories) | Infinity | Never (or Coach-managed) |
| `agent-session-{session_id}` | 365 days | Auto-expire after 1 year |
| `agent-sessions_{user_id}` | Infinity | Never |
| `vault` | Infinity | Never |
| `obsidian` | Infinity | Never |

TTL is determined by the `memory_bank` parameter: banks starting with `agent-session-` get 365 days; all others get no expiry (NULL `valid_until`).

### sleep() Becomes a No-Op

The `sleep()` use case now returns a no-op response since all memories are already in episodic memory:
```python
return { consolidated: false, reason: "all memories already in episodic tier" }
```

### Content is Stored Verbatim

No summarization — episodic memory stores content exactly as provided. This is critical for:
- Node memories (one-step instructions must be preserved exactly)
- User profile memories (verbatim preferences and facts)

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Use `consolidate_to_episodic()` API | Uses existing Mnemosyne API | Requires `source_wm_ids` (working memory IDs); designed for consolidating multiple rows into a summary, not storing new content verbatim | Would require fabricating a working memory row first, then consolidating — unnecessarily complex |
| Pin memories in working memory | No architecture change | Requires Mnemosyne API change to support `pinned=1` in `remember()` | More complex than moving to episodic; requires library changes |
| Add reconciliation to bensyne | Detects missing memories and re-ingests | Doesn't prevent the trim in the first place | More complex; reactive instead of proactive |
| Add TTL parameter to Racochu API | Source-specific TTL | Increases blast radius of change | Racochu already passes `memory_bank` parameter, which is sufficient for TTL determination |

## Consequences

- **Positive:** Decision tree nodes no longer expire after 7 days; episodic memory stores content verbatim (no summarization loss); source-specific TTL policies enable operational state to expire while durable memories persist; read-only verification tools (`getFileChunks`, `searchFiles`, `expandFileRelations`, `recallMemory`) require no changes — they already check both tables.
- **Negative:** Working memory is designed for short-term, high-churn data; episodic is for durable storage. By moving everything to episodic, we're treating all memories as long-term (acceptable because bensyne-managed memories are intentionally durable). The Coach skill must still manage occasional memory expiry via `valid_until` in metadata.
- **Neutral:** Migration script ran successfully on production database (0 rows — database was empty). The `sleep()` API remains for backward compatibility but is documented as a no-op.

## Verification

- Unit tests: 33 tests in `test_mnemosyne_client.py` (including forget/update tests), 8 in `test_mnemosyne_client_save_episodic.py`, 6 in `test_mnemosyne_client_remember_episodic.py`, 5 in `test_migrate_working_to_episodic.py`, 3 in `test_update_sleep_use_cases.py` — all passing.
- Manual verification against episodic_memory table: INSERT, UPDATE, DELETE all work correctly.
- Full test suite: 2078 tests, 2056 passing (23 pre-existing failures unrelated to this change), 9 skipped.
- Migration script ran successfully on production database.
