---
type: decision
id: DEC-0064
system: bensyne-mcp
title: "Layered Bank Components — Application MemoryBankService + Infrastructure MemoryBankRouter"
status: accepted
createdAt: "2026-08-23T14:33:06Z"
updatedAt: "2026-08-23T14:33:06Z"
tags: [memory-bank, ddd, layering, service, router, infrastructure]
supersedes: []
superseded_by: []
see_also:
  - concepts/0003-memory-bank-aggregate.concept.md
  - decisions/0008-sqlite-hash-index.decision.md
  - decisions/0011-result-pattern-error-handling.decision.md
---

# DEC-0064: Layered Bank Components — Application `MemoryBankService` + Infrastructure `MemoryBankRouter`

## Context

Path rules were duplicated/contradicted across `mnemosyne_client.py:48-53`, `bank_manager.py:29-32`, `handlers.py` (6 sites), `di.py:127-144`, `hash_index_service.py:141-145` (CWD-relative). The instance pool + client factory live in `MemoryBankRouter` (existing class, `router.py:24-146`); descriptions lived in the in-memory `MemoryBankRegistry`. Round 4 collapsed everything into one `MemoryBankService`; round 5 (U14) restores proper DDD layering: application logic vs infrastructure.

## Decision

Two components with distinct roles (per business logic + layer, U14):

- **`MemoryBankService`** (application, `src/application/services/memory_bank_service.py`) — business operations only: `register_memory_bank` / `get_memory_bank` / `list_memory_banks` / `ensure_default_bank`, orchestrated over `MemoryBankRepository` + `MemoryBank` aggregate. No path resolution, no pool. Pattern: `FileService`.
- **`MemoryBankRouter`** (infrastructure, `src/infrastructure/bank/router.py`) — restored from the existing class with two changes:
  1. **Registry duties removed** (`self.registry`, `get_bank_description`, `register_bank` — `registry.py` deleted; descriptions persist via the repository, DEC-0063).
  2. **Path authority added**: `get_bank_dir`, `get_bank_db_path`, `get_file_metadata_path`, `get_hash_index_path`, `list_bank_dirs` (rules moved from the deleted `mnemosyne/bank_manager.py`).
  Pool mechanics unchanged: `instances`, `get_instance` (double-checked locking + LRU eviction via `pool.evict_if_over_limit`), default instance at boot, health helpers.

Wiring: handlers/DI take the router for technical wiring (paths, client instances — repo convention; handlers already take the router today); MCP business operations go through `MemoryBankService` via use cases. `HashIndexService`'s CWD-relative default is removed — explicit `db_path` required. A module-level `memory_banks_db_path(data_dir)` helper breaks the circular constructor dependency (repository needs the db path).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Single `MemoryBankService` doing everything (round 4) | One component | Mixes application + infrastructure; service too large; user asked for layered DDD | Round-5 U14 |
| `MemoryBankManagerService` (round 3) | Path+metadata in one infra class | Artificial middle layer between service and repository; no distinct business logic | Round-4 U13 veto |
| Free functions in `data_dir.py` | Fewer classes | Muddles root-only contract | Keeps layering clean |
| Paths in the application service | Tools see one API | Paths are infrastructure, not business logic (U14) | Router owns paths |

## Consequences

- **Positive:** Correct DDD layering: domain (`MemoryBank`) → infrastructure (`MemoryBankRepository`, `MemoryBankRouter`) → application (`MemoryBankService`) → interface (use cases/handlers). Router pool logic untouched (already tested); path rules move from `BankManager` into the router (one infrastructure authority). Business operations exposed via one application service; technical wiring stays with the infrastructure the codebase already injects.
- **Negative:** Two components to wire instead of one — but the router already exists and is injected today (minimal churn). Touches former `BankManager` call sites (P3/P4) — mechanical, test-covered.
