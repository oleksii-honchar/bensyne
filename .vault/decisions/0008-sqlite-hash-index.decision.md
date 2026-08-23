---
type: decision
id: DEC-0008
system: bensyne-mcp
title: "Use SQLite HashIndex for File Hash Deduplication"
status: accepted
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [deduplication, hash-index, sqlite]
see_also:
  - decisions/0061-canonical-bank-data-layout.decision.md
  - concepts/0001-hash-index.concept.md
  - decisions/0048-dual-hash-wire-contract.decision.md
---

# DEC-0008: Use SQLite HashIndex for File Hash Deduplication

## Context

Bensyne needs a fast, exact-match index to check for duplicate file hashes before creating memories. The originally designed triple store approach was not viable — Mnemosyne lacks `triple_query`/`triple_add` API.

## Decision

Use a SQLite-backed HashIndex per memory bank at `data/{memory_bank}/hash_index.db`. The `HashIndex` class provides `lookup(file_hash)`, `store(file_hash, memory_id)`, and `remove(memory_id)` operations.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS hash_index (
    file_hash TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL
);
```

- Upsert via SQLAlchemy ORM (`HashIndexService`): `session.get(HashIndexRow, file_hash)` → add new row or update `memory_id` in place (no raw `INSERT OR REPLACE`)
- WAL mode for concurrent reads
- Per-memory-bank isolation (separate DB file per bank)

## Rationale

1. **SQLite already in dependency tree** — Mnemosyne uses it, no new dependency needed
2. **WAL mode supports concurrent reads** — no "database is locked" errors under load
3. **Exact-match** — deterministic, O(1) lookup, no false positives
4. **Persistent** — survives restarts (unlike in-memory approaches)
5. **Per-bank isolation** — no cross-contamination between memory banks

## Alternatives Considered

1. **Mnemosyne triple store** — no `triple_query`/`triple_add` API available
2. **In-memory dictionary** — lost on restart, no persistence
3. **Redis** — external dependency, overkill for this use case

## Consequences

- **Positive:** Simple, persistent, fast exact-match lookups, no external dependencies
- **Negative:** Additional SQLite file per memory bank
- **Mitigation:** SQLite is already a dependency; WAL mode supports concurrent access

## Status Note

> **2026-08-23:** Stated path `data/{memory_bank}/hash_index.db` is **superseded** by the canonical v2 layout `data/banks/<bank>/hash_index.db` (DEC-0062). Path resolution now flows from the `MemoryBankRouter` path authority (`get_hash_index_path`, `src/infrastructure/bank/router.py:158`). The pre-vault ADR-005 path rules (previously documented in the `mnemosyne/bank_manager.py` docstring) are likewise superseded by the router; `bank_manager.py` was deleted in the bank layout normalization round.
