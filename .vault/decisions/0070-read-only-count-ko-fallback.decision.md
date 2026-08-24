---
type: decision
id: DEC-0071
system: bensyne-mcp
title: "Read-Only Count Semantics — Result.ko on Missing/Corrupt DB, Fallback to Stored Value"
status: accepted
createdAt: "2026-08-23T20:04:39Z"
updatedAt: "2026-08-23T20:04:39Z"
tags: [memory-bank, error-handling, result-pattern, mnemosyne, read-only]
supersedes: []
superseded_by: []
see_also:
  - decisions/0069-live-memory-count-non-pooled-banks.decision.md
  - decisions/0011-result-pattern-error-handling.decision.md
---

# DEC-0071: Read-Only Count Semantics — Result.ko Fallback

## Context

A bank may exist in the registry without a `mnemosyne.db` (never initialized) or with a corrupt DB. The count path must not fabricate values and must not create files on a listing.

## Decision

`router.get_stats_for()` returns `Result.ko(MEMORY_BANK_DB_NOT_FOUND)` when the bank's `mnemosyne.db` does not exist. `ListBanksUseCase` keeps the existing (stored or 0) `memory_count` and logs a warning. Only a successful `get_stats()` replaces the value. Never fabricate counts; a missing DB keeps the registry's stored count.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| `Result.ok(0)` on missing DB | Simpler | Treats "never initialized" as "empty"; ambiguous, can mask real errors | Ambiguity is dangerous |
| Constructing client for missing DB | Uniform code path | Would mkdir bank dir + create db file on a listing | Side effects on read operation |

## Consequences

- **Positive:** Honest fallback; listing is read-only; no dir/db creation on a listing.
- **Negative:** None significant — the ko path is well-tested with real and mocked clients.
