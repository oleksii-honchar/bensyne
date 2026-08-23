---
type: decision
id: DEC-0066
system: bensyne-mcp
title: "get_stats Banks List via Bensyne Scan + Phantom Cleanup"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, get-stats, mnemosyne, phantom-dir, workaround]
supersedes: []
superseded_by: []
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0064-unified-list-memory-banks.decision.md
---

# DEC-0066: `get_stats` Banks List via Bensyne Scan + Phantom Cleanup

## Context

Library bug (mnemosyne 3.15.1 `memory.py:531-535`): `Mnemosyne.get_stats()` constructs a library `BankManager(data_dir=Path(db_path).parent)` which eagerly mkdirs and scans `parent/banks/`. Under DEC-0062 it misfires for **every** bank — phantom nested `banks/` dirs on every `getMemoryStats` call, plus a wrong banks list.

## Decision

Bensyne-side workaround in `MnemosyneClient.get_stats()`: after the library call, (1) overwrite the `banks` key with `router.list_bank_dirs()` and (2) remove the phantom `<bank_dir>/banks/` when empty (warn + leave when non-empty). No library fork/pin change; no upstream report (U12).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Fork/patch mnemosyne locally | Fixes root cause | Vendor fork; maintenance burden | Workaround is ~10 lines and testable |
| Avoid `get_stats()` entirely | No side effect | Stats consumed by tools + health checks | Only the `banks` key is wrong |

## Consequences

- **Positive:** No phantom dirs from bensyne traffic; `getMemoryStats.banks` = canonical view (DEC-0065).
- **Negative:** Direct library users (non-bensyne) still hit the bug — out of scope (U3, U12).
