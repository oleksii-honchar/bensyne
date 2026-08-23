---
type: decision
id: DEC-0062
system: bensyne-mcp
title: "Canonical Bank Data Layout — data/banks/<bank>/ for All DB Files"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, data-layout, paths, registry, v2-layout]
supersedes: []
superseded_by: []
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0008-sqlite-hash-index.decision.md
  - decisions/0013-sqlite-file-metadata-storage.decision.md
---

# DEC-0062: Canonical Bank Data Layout — `data/banks/<bank>/` for All DB Files

## Context

Four subsystems resolved per-bank paths with three different patterns: mnemosyne used `data/mnemosyne.db` (default) vs `data/banks/<bank>/mnemosyne.db`; file metadata handlers used top-level `data/<bank>/file_metadata.db`; the bank-type checker used `data/file_metadata.db` / `data/banks/<bank>/…`; hash index used CWD-relative `Path("data")/<bank>/hash_index.db`. Observed consequences: split-brain bank data, wrong default-bank classification on the forget path, stray `data/bank/` artifacts, latent CWD bug under Docker.

## Decision

Single canonical layout for **every** bank, including `default` (no root special-case — U11):

```
<data_dir>/memory_banks.db                     # bank registry (DEC-0063, U10)
<data_dir>/banks/<bank>/mnemosyne.db
<data_dir>/banks/<bank>/file_metadata.db
<data_dir>/banks/<bank>/hash_index.db
```

All path resolution flows from `MemoryBankRouter` path authority (DEC-0064). **No migration** (U4): the user wiped all v1 data; the v2 tree is created fresh on first boot (repository bootstrap + lazy mkdir per bank). A stray v1 tree, if ever reappearing, is an operator concern (manual move per U12), not automated behavior.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| A. `data/<bank>/…` (no `banks/` nesting) | Flatter | "banks/" is mnemosyne-oss convention | User chose `banks/` (U1) |
| C. Minimal fix (only hash_index + checker) | Smallest diff | Perpetuates 3 different patterns | User directed normalization |
| Keep default at root `data/mnemosyne.db` | Preserves library convention | Mixed layout; if/else everywhere; get_stats bug fires for default | U1 "same approach … for both" — uniform wins; U11 confirms |

## Consequences

- **Positive:** Every bank is a self-contained directory; backup = `cp -r banks/<bank>`; deletion is atomic. Checker/handlers/client/hash-index mismatches become structurally impossible (one authority). Clean-slate bootstrap: no migrator code, no migration risk (U4).
- **Negative:** Departs from mnemosyne-oss library's own `BankManager` convention — bensyne always passes explicit `db_path`, so the library convention never applies.
- **Supersedes:** the pre-vault ADR-005 path rules in `bank_manager.py` docstring; DEC-0008's stated path.
