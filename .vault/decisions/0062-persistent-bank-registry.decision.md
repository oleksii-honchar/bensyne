---
type: decision
id: DEC-0063
system: bensyne-mcp
title: "Persistent Bank Registry — memory_banks.db, Persisting the MemoryBank Aggregate"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, registry, sqlite, persistence, aggregate]
supersedes: [DEC-0003, DEC-0006]
superseded_by: []
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0003-in-memory-namespace-registry.decision.md
  - decisions/0006-in-memory-namespace-registry.decision.md
---

# DEC-0063: Persistent Bank Registry — `memory_banks.db`, Persisting the `MemoryBank` Aggregate

## Context

Bank descriptions lived in an in-memory dict (`MemoryBankRegistry._descriptions`), written by `registerMemoryBank`, wiped on every restart. DEC-0003/DEC-0006 accepted that loss on the rationale "external systems re-register at startup" — fragile in practice: racochu only re-sends descriptions for sources that have one configured (none currently in `~/.config/racochu.yaml`), only while it runs. Result observed: banks listed with empty descriptions — agents cannot tell when/why to use a bank. User (U2): "we need to store this info somewhere."

A proper `MemoryBank` domain aggregate ALREADY EXISTED (`src/domain/memory_bank_aggregate.py` — name, description, status, created_at, last_accessed, memory_count, memories; `of()` factory; activate/suspend/remember/forget) with a matching repository contract in the test fake (`InMemoryMemoryBankRepository`: save/find_by_id/list/delete). It was never wired to production. User (U9): use this legit entity — wrap persistence around it, don't invent a raw `Bank`.

## Decision

Persist memory banks in SQLite at the data root: `<data_dir>/memory_banks.db` (U10), table `memory_banks(name TEXT PRIMARY KEY, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'registered', created_at TEXT, last_accessed TEXT, memory_count INTEGER NOT NULL DEFAULT 0)` — mirrors the aggregate fields (`memories` collection excluded: memories live in mnemosyne.db).

DDD wiring:
- **`MemoryBank`** (domain, EXISTING): kept as THE entity. Single extension: `update_description(description)` (frozen update, validated via `MemoryBankSchema`) for re-registration.
- **`MemoryBankRepository`** (NEW infrastructure, `src/infrastructure/bank/memory_bank_repository.py`): SQLAlchemy + WAL + `create_all` fresh bootstrap (DEC-0008 precedent — no migration framework); Result-returning; `ON CONFLICT(name) DO UPDATE`; method contract matches the existing `InMemoryMemoryBankRepository` fake.
- **`MemoryBankService`** (application): business orchestration — `register_memory_bank` / `get_memory_bank` / `list_memory_banks` + `ensure_default_bank` (idempotent startup seed). No paths, no pool (U14).

`registerMemoryBank` writes via `MemoryBankService` → `MemoryBankRepository`; `listMemoryBanks` reads the same way; the in-memory `MemoryBankRegistry` is deleted.

Compatibility (verified): racochu's `registerBanks` filters to sources WITH non-empty descriptions only (`file-watcher.service.ts:47-68`), so the strict `MemoryBank.of()` factory does not break it. `registerMemoryBank` with an empty description now returns a tool error (domain invariant) — documented behavior tightening.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Raw `Bank` entity (round 2) | Lean | Two competing bank concepts; violates U9 | Round-3 user veto |
| Per-bank sidecar JSON next to banks | Co-located; no extra DB | Scattered metadata | User: memory_banks.db (U10) |
| Rows inside each mnemosyne.db | No new file | Library-owned schema; coupling | bensyne metadata in bensyne-owned files |
| Keep in-memory + force racochu re-send | Zero storage | Still lost between startups | Does not satisfy U2 |

## Consequences

- **Positive:** `registerMemoryBank` finally matches its documented contract (durable registration). Descriptions survive restarts independent of racochu; agents get stable bank semantics. The pre-existing `MemoryBank` aggregate becomes production-live; its domain tests and the `InMemoryMemoryBankRepository` fake contract are reused instead of discarded.
- **Negative:** New file at data root (`memory_banks.db`). Supersedes DEC-0003/DEC-0006 (2026-08-16).
